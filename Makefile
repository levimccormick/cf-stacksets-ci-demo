up:
	aws --region us-east-1 s3 cp stacks s3://source-bucket/stacks/ --recursive

validate:
	aws --region us-east-1 cloudformation validate-template \
		--template-body "file://stacks/stack.cf.json"

create-stack-set:
	aws --region us-east-1 cloudformation create-stack-set --stack-set-name cf-ss-demo \
		--parameters ParameterKey=ProjectName,ParameterValue=CFDemo \
		--tags Key=project,Value=cf_demo \
		--capabilities CAPABILITY_NAMED_IAM \
		--template-body "file://stacks/stack.cf.json"

update-stack-set:
	aws --region us-east-1 cloudformation update-stack-set --stack-set-name cf-ss-demo \
		--template-body "file://stacks/stack.cf.json"

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
		-e template_path=/code/team_templates \
 		stack-set-deployer python deploy.py

bash:
	docker run --rm -it -v `pwd`:/code stack-set-deployer bash

deploy-cfn-container:
	docker build -t deploy-ta-codebuild -f $(shell pwd)/Dockerfile.deploycfn .

deploy-cfn: deploy-cfn-container
	docker run --rm -it \
			-v $(shell pwd):/code \
			deploy-ta-codebuild \
			aws --region us-east-1 cloudformation deploy  \
			--template-file code/deployment/stack_set_cf.json \
			--stack-name team-access-sample \
			--capabilities CAPABILITY_IAM \
			--tags sps:unit=techops \
			--tags sps:product=cloud-engineering \
			--tags sps:subproduct=account-standup \
			--tags sps:env=dev
