up:
	aws --region us-east-1 s3 cp stacks s3://source-bucket/stacks/ --recursive

validate:
	aws --region us-east-1 cloudformation validate-template \
		--template-body "file://stacks/stack.json"

create-stack-set:
	aws --region us-east-1 cloudformation create-stack-set --stack-set-name cf-ss-demo \
		--parameters ParameterKey=ProjectName,ParameterValue=CFDemo \
		--tags Key=project,Value=cf_demo Key=version,Value=$$(git rev-parse HEAD) \
		--capabilities CAPABILITY_NAMED_IAM \
		--template-body "file://stacks/stack.json"

update-stack-set:
	aws --region us-east-1 cloudformation update-stack-set --stack-set-name cf-ss-demo \
		--tags Key=project,Value=cf_demo Key=version,Value=$$(git rev-parse HEAD) \
		--template-body "file://stacks/stack.json"

create-instances:
	aws --region us-east-1 cloudformation create-stack-instances --stack-set-name cf-ss-demo \
		--regions us-east-1 us-east-2 us-west-2 \
		--operation-preferences MaxConcurrentPercentage=100 \
		--accounts 824315082068

delete-instances:
	aws --region us-east-1 cloudformation delete-stack-instances --stack-set-name cf-ss-demo \
		--regions us-east-1 us-east-2 us-west-2 \
		--no-retain-stacks \
		--accounts 824315082068

build:
	docker build -t stack-set-deployer -f Dockerfile.localrun .

deploy:
	docker run --rm -it -v `pwd`:/code -w /code \
		-e path=/code/stacks \
 		stack-set-deployer python deploy.py

bash:
	docker run --rm -it -v `pwd`:/code stack-set-deployer bash

create-automation:
	aws --region us-east-1 cloudformation create-stack --stack-name stack-set-deployer \
		--tags Key=project,Value=cf_demo Key=version,Value=$$(git rev-parse HEAD) \
		--capabilities CAPABILITY_NAMED_IAM \
		--template-body "file://automation/stackset-deployer.json"