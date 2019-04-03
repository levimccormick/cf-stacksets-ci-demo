import os
from time import sleep
import boto3
import yaml

cf = boto3.client('cloudformation', region_name='us-east-1')
s3_bucket = os.environ['SOURCE_BUCKET']

def put_stack_set(stack_name, file_name):
    ''' Create or Update the stack set, depending on the current status of the
        stack set.
        Returns the operation id for async processing.
    '''
    # check to see if stack set exists
    stack_exists = False
    timer = 1
    while True:
        try:
            response = cf.describe_stack_set(StackSetName=stack_name)
            if response['StackSet']['Status'] == 'ACTIVE':
                stack_exists = True
                break
        except cf.exceptions.StackSetNotFoundException as e:
                break
        except cf.exceptions.RequestLimitExceeded as e:
            print("Cloudformation Throttling. Retrying...")
            sleep(timer)
            timer = timer + 1
    print(f"https://s3.amazonaws.com/{s3_bucket}/stacks/{file_name}")
    if stack_exists:
        # Stack exists and is healthy, run stack update.
        print(f"{stack_name} exists, updating...")
        timer = 1
        while True:
            try:
                response = cf.update_stack_set(
                    StackSetName=stack_name,
                    TemplateURL=f"https://s3.amazonaws.com/{s3_bucket}/stacks/{file_name}",
                    Capabilities=['CAPABILITY_NAMED_IAM',],
                    Tags=[
                        {'Key': 'project','Value': 'cf_demo'},
                        {'Key': 'version','Value': 'git-sha-here'},
                    ]
                )
                break
            except cf.exceptions.RequestLimitExceeded as e:
                print("Cloudformation Throttling. Retrying...")
                sleep(timer)
                timer = timer + 1

        return response['OperationId']
    else:
        # Stack needs to be created
        print(f"{stack_name} does not exist, creating...")
        timer = 1
        while True:
            try:
                response = cf.create_stack_set(
                    StackSetName=stack_name,
                    TemplateURL=f"https://s3.amazonaws.com/{s3_bucket}/stacks/{file_name}",
                    Capabilities=['CAPABILITY_NAMED_IAM',],
                    Tags=[
                        {'Key': 'project','Value': 'cf_demo'},
                        {'Key': 'version','Value': 'git-sha-here'},
                    ]
                )
                break
            except cf.exceptions.RequestLimitExceeded as e:
                print("Cloudformation Throttling. Retrying...")
                sleep(timer)
                timer = timer + 1
        return "Creating"


def determine_instances(stack_name, accounts, regions):
    ''' This function determines which stack set instances need to be created
        and deleted.
     '''
    # Grab existing instances
    timer = 1
    while True:
        try:
            response = cf.list_stack_instances(
                StackSetName=stack_name
            )
            break
        except cf.exceptions.RequestLimitExceeded as e:
            print("Cloudformation Throttling. Retrying...")
            sleep(timer)
            timer = timer + 1
    current_accounts = [item['Account'] for item in response['Summaries']]
    print(f"Currently deployed in these accounts: {current_accounts}")

    # Compare existing instances to desired instances
    unwanted_accounts = list(set(current_accounts).difference(accounts))
    wanted_accounts = list(set(accounts).difference(current_accounts))
    print(f"We need to remove these: {unwanted_accounts}")
    print(f"We need to add these: {wanted_accounts}")


    return (wanted_accounts, unwanted_accounts)

def delete_instances(stack_name, accounts, regions):
    ''' Remove unnecessary stack set instances.
     '''
    # Delete
    timer = 1
    while True:
        try:
            response = cf.delete_stack_instances(
                StackSetName=stack_name,
                Accounts=accounts,
                Regions=regions,
                OperationPreferences={
                    'FailureTolerancePercentage': 100,
                    'MaxConcurrentPercentage': 100
                },
                RetainStacks=False
            )
            break
        except cf.exceptions.RequestLimitExceeded as e:
            print("Cloudformation Throttling. Retrying...")
            sleep(timer)
            timer = timer + 1

    return response['OperationId']

def create_instances(stack_name, accounts, regions):
    ''' Remove unnecessary stack set instances.
     '''
    # Delete
    timer = 1
    while True:
        try:
            response = cf.create_stack_instances(
                StackSetName=stack_name,
                Accounts=accounts,
                Regions=regions,
                OperationPreferences={
                    'FailureTolerancePercentage': 100,
                    'MaxConcurrentPercentage': 100
                }
            )
            break
        except cf.exceptions.RequestLimitExceeded as e:
            print("Cloudformation Throttling. Retrying...")
            sleep(timer)
            timer = timer + 1

    return response['OperationId']

def wait_for_cf_ops(operations):
    ''' Takes a list of operation ids from Cloudformation and waits for them
        to complete.
    '''
    timer = 1
    while operations:
        for stack_name in list(operations.keys()):
            if operations[stack_name] == "Creating":
                operations.pop(stack_name, None)
            else:
                response = cf.describe_stack_set_operation(
                    StackSetName=stack_name,
                    OperationId=operations[stack_name])
                if response['StackSetOperation']['Status'] in ['RUNNING','STOPPING']:
                    print(f"Stack {stack_name} running.")
                    pass
                elif response['StackSetOperation']['Status'] in ['FAILED','STOPPED']:
                    print(f"Stack {stack_name} failed.")
                    operations.pop(stack_name, None)
                    # put something to alert on here
                elif response['StackSetOperation']['Status'] in ['SUCCEEDED']:
                    print(f"Stack {stack_name} updated sccessfully.")
                    operations.pop(stack_name, None)
                    # when a stack completes, reset the back off since other stacks should finish about the same time
                    timer = 1

        # back off api calls, max of one minute
        # print(f"Sleeping {timer}.")
        sleep(timer)
        timer = 60 if timer * 2 > 60 else timer * 2


def main():
    # read in config file
    print("Loading account config...")
    with open ("account_config.yml", "r") as myfile:
        try:
            teams = yaml.safe_load(myfile)
        except yaml.YAMLError as exc:
            print(exc)

    # set default config for all teams
    default_config = teams.pop('all', None)

    operations = {}
    # loop over team files and deploy stacks
    print("Creating stack sets...")
    directory = os.fsencode(os.environ.get('template_path'))
    files = []
    for f in os.listdir(directory):
         filename = os.fsdecode(f)
         if filename.endswith(".json"):
            file = f.decode("utf-8")
            files.append(file)
            stack_name = file.split('.')[0]
            operations[stack_name] = put_stack_set(stack_name, file)
    # Let's make sure all stack set operations finish
    wait_for_cf_ops(operations)

    # now that all stack sets are created or updated, create the stack instances
    operations = {}
    unwanted_stacks = {}
    for file in files:
        # Check for special region/account configuration
        if file in teams.keys():
            # These lists need to be unique values
            regions = list(set().union(default_config.get('regions', []), teams[file].get('regions', [])))
            accounts = list(set().union(default_config.get('accounts',[]), teams[file].get('accounts',[])))
        else:
            regions = default_config.get('regions', [])
            accounts = default_config.get('accounts',[])

        stack_name = file.split('.')[0]
        (wanted_accounts, unwanted_stacks[stack_name]) = determine_instances(stack_name, accounts, regions)
        if wanted_accounts:
            operations[stack_name] = create_instances(stack_name, wanted_accounts, regions)
    # Let's make sure all stack set instances are created
    wait_for_cf_ops(operations)

    # Remove unwanted instances
    for stack_name in unwanted_stacks.keys():
        if unwanted_stacks[stack_name]:
            operations[stack_name] = delete_instances(stack_name, unwanted_stacks[stack_name], regions)
    wait_for_cf_ops(operations)

if __name__ == '__main__':
    main()
