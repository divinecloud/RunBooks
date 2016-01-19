import boto3
from boto3.session import Session
import json
import time
import sys
#open the json file

fjson=open(sys.argv[1],"r+")
wfile=open(sys.argv[2],"w+")
#Read the json file
jsond=json.loads(fjson.read())
rb=jsond["runbook"]
try:
    print("Retrieving AWS Access Key, Secret Key, Region from json")
    #Get the aws access key
    for i in rb:
        if i["name"]=="AWS_ACCESS_KEY":
            aws_access=i["value"]

    if(aws_access==""):
        raise ValueError("AWS_ACCESS_KEY is not given in the json")

    #Get the secret key
    for i in rb:
        if i["name"]=="AWS_SECRET_KEY":
            aws_secret=i["value"]

    if(aws_secret==""):
        raise ValueError("AWS_SECRET_KEY is not given in the json")

    #Get the region
    for i in rb:
        if i["name"]=="AWS_REGION":
            reg_name=i["value"]

    if(reg_name==""):
        raise ValueError("AWS_REGION is not given in the json")

    print("Starting session with the provided Access key, Secret key and Region in the json")
    #Starting session
    session = Session(aws_access_key_id=aws_access,
                      aws_secret_access_key=aws_secret,
                      region_name=reg_name)

    print("Session Started")

    ec2 = session.resource('ec2')
    ec2client=session.client('ec2')

    for i in rb:
        if i["name"]=="VPC_Name":
            vpc_name=i["value"]
    if(vpc_name==""):
        raise ValueError("VPC Name is not given in the json")

    for i in rb:
        if i["name"]=="VPC_CIDR":
            vpc_cidr=i["value"]
    if(vpc_cidr==""):
        raise ValueError("VPC cidr is not given in the json")

    print("Creating VPC with the given VPC Name and CIDR in json")

    #Creating VPC
    vpc = ec2.create_vpc(CidrBlock=vpc_cidr)
    vpchandler=ec2.Vpc(vpc.id)
    vpchandler.create_tags(
        Tags=[
            {
                'Key':'Name',
                'Value':vpc_name
            },
        ]
    )

    print("VPC Created")

    print("Creating internet gateway")
    #Creating Internet Gateway and attaching to vpc
    gateway = ec2.create_internet_gateway()
    internet_gateway = ec2.InternetGateway(gateway.id)
    internet_gateway.attach_to_vpc(
        VpcId=vpc.id
    )

    print("Created internet gateway and attached to vpc")

    route_table_iterator = vpchandler.route_tables.filter(
        Filters=[
            {
                'Name': 'association.main',
                'Values':[
                        'true',
                    ]
            }
            ]
        )
    for j in route_table_iterator:
        routeid_public=j.id
    route_table = vpchandler.create_route_table()
    routeid_private=route_table.id
    print("Getting route table id")

    for i in rb:
        if i["name"]=="Subnets":
            subnetj=i["value"]
    if(subnetj==""):
        raise ValueError("Subnets not given in the json")
    subnetjson=json.loads(subnetj)

    subs=[]

    route_table_public = ec2.RouteTable(routeid_public)
    route_table_private = ec2.RouteTable(routeid_private)
    b=0

    print("Creating subnets")

    #Creating subnets
    for subnet in subnetjson:

        if(subnet["Public"]=="yes"):
            if(subnet["CIDR"]==""):
                raise ValueError("Missing CIDR in a subnet in json")
            psub=vpc.create_subnet(CidrBlock=subnet["CIDR"])
            subs.append(psub)
            subhandler=ec2.Subnet(psub.id)
            tag = subhandler.create_tags(
            Tags=[
                {
                    'Key': 'Name',
                    'Value': subnet["Name"]
                },
            ]
            )
            if(b==0):
                b=1
                natinssub=psub.id
            route_table_association = route_table_public.associate_with_subnet(
            SubnetId=psub.id,
            )
        else:
            if(subnet["CIDR"]==""):
                raise ValueError("Missing CIDR in a subnet in json")
            psub=vpc.create_subnet(CidrBlock=subnet["CIDR"])
            subs.append(psub)
            subhandler=ec2.Subnet(psub.id)
            tag = subhandler.create_tags(
            Tags=[
                {
                    'Key': 'Name',
                    'Value': subnet["Name"]
                },
            ]
            )
            route_table_association = route_table_private.associate_with_subnet(
            SubnetId=psub.id,
            )
    print("Created subnets")

    #Creating route
    print("Creating route")
    response = route_table_public.create_route(
        DestinationCidrBlock='0.0.0.0/0',
        GatewayId=gateway.id,
    )

    print("Route created")

    for i in rb:
        if i["name"]=="SecurityGroupName":
            sgname=i["value"]
    if(sgname==""):
        raise ValueError("Security group not given in the json")

    print("Creating security group")

    #Creating security group
    sg = ec2.create_security_group(
        GroupName=sgname,
        Description=sgname,
        VpcId=vpc.id
    )

    print("Security group created")

    #Tagging security group
    print("Tagging Security Group")
    security_group = ec2.SecurityGroup(sg.id)
    security_group.create_tags(
        Tags=[
            {
                'Key': 'Name',
                'Value': sgname
            },
        ]
    )


    for i in rb:
        if i["name"]=="SecurityRules":
            srules=i["value"]

    print("Attaching security group")

    print(sg.id)

    #Attaching rules to security group
    jsrule=json.loads(srules)
    for iterules in jsrule:
        if "-" in iterules['Port']:
            temp=iterules['Port'].split("-")
            fport=temp[0]
            tport=temp[1]
        else:
            fport=iterules['Port']
            tport=iterules['Port']
        if iterules['Protocol']=="all":
            prot="-1"
        else:
            prot=iterules['Protocol']
        #print(prot, fport, tport)
        security_group.authorize_ingress(
            GroupId=sg.id,
            IpProtocol=prot,
            FromPort=int(fport),
            ToPort=int(tport),
            CidrIp=iterules['CIDR'],
        )

    print("Security groups attached")

    for i in rb:
        if i["name"]=="NAT":
            nats=i["value"]
    if(nats==""):
        for sub in subnetjson:
            if(sub['AttachToNAT']=='yes'):
                raise ValueError("AttachToNat is given as yes. But, no nat instance details are given")

    else:
        allnat=json.loads(nats)
        finst=[]
        print("Starting NAT instance")
        #Starting nat instance
        for nat in allnat:
            instance = ec2.create_instances(
                ImageId=nat['AMI'],
                MinCount=1,
                MaxCount=1,
                KeyName=nat["KeyPairName"],
                InstanceType='t1.micro',
                Monitoring={
                    'Enabled': True
                },
                InstanceInitiatedShutdownBehavior='stop',
                NetworkInterfaces=[
                    {
                        'DeviceIndex': 0,
                        'SubnetId': natinssub,
                        'Description': 'Nat Instance',
                        'Groups': [
                            sg.id,
                        ],
                        'PrivateIpAddress': nat['IP'],
                        'DeleteOnTermination': True,
                        'AssociatePublicIpAddress': True
                    },
                ],
            )
            time.sleep(5)
            finst.append([instance[0].id,nat["Name"],"yes",nat["KeyPairName"]])
            inshandler=ec2.Instance(instance[0].id)
            inshandler.create_tags(
            Tags=[
                {
                    'Key': 'Name',
                    'Value': nat["Name"]
                },
            ]
            )

    print("NAT instance created")

    for i in rb:
        if i["name"]=="Instances":
            insj=i["value"]


    insts=json.loads(insj)

    print("Creating instances")

    #Creating other instances
    for ins in insts:
        #Getting the security group id
        sgs=ec2client.describe_security_groups(
            Filters=[
                    {
                            'Name': 'group-name',
                            'Values':[
                                    ins['SecurityGroupName'],
                                    ]
                            },
                    {
                        'Name': 'vpc-id',
                        'Values':[
                            vpc.id
                            ]
                        },
                    ]
            )
        sgpid=sgs['SecurityGroups'][0]['GroupId']

        #Getting the subnet id
        subn=ec2client.describe_subnets(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values':[
                        ins['SubnetName']
                        ]
            },
            {
                'Name': 'vpc-id',
                'Values':[
                    vpc.id
                    ]
                }
        ]
        )
        subid=subn["Subnets"][0]['SubnetId']
        if(ins['AutoGeneratePublicIP']=='yes'):
            instance = ec2.create_instances(
            ImageId=ins['AMI'],
            MinCount=1,
            MaxCount=1,
            KeyName=ins["keyPairName"],
            InstanceType=ins['Type'],
            Monitoring={
                'Enabled': True
            },
            InstanceInitiatedShutdownBehavior='stop',
            NetworkInterfaces=[
                {
                    'DeviceIndex': 0,
                    'SubnetId': subid,
                    'Description': 'Ec2 Instance',
                    'PrivateIpAddress': ins['IP'],
                    'Groups': [
                        sgpid,
                    ],
                    'DeleteOnTermination': True,
                    'AssociatePublicIpAddress': True
                },
            ],
            )
            #Collecting instance details
            finst.append([instance[0].id,ins["InstanceName"],'yes',ins["keyPairName"]])
        else:
            instance = ec2.create_instances(
            ImageId=ins['AMI'],
            MinCount=1,
            MaxCount=1,
            KeyName=ins["keyPairName"],
            SecurityGroupIds=[
            sgpid,
            ],
            InstanceType=ins['Type'],
            Monitoring={
                'Enabled': True
            },
            SubnetId=subid,
            PrivateIpAddress=ins['IP'],
            InstanceInitiatedShutdownBehavior='stop',
            )
            #Collecting instance details
            finst.append([instance[0].id,ins["InstanceName"],'no',ins["keyPairName"]])
        time.sleep(5)
        inshandler=ec2.Instance(instance[0].id)
        print("Created: "+instance[0].id)
        print("Attaching Tags to instance")
        #Attaching Tags

        inshandler.create_tags(
        Tags=[
            {
                'Key': 'Name',
                'Value': ins["InstanceName"]
            },
        ]
        )


    print("Instances created")

    print("Retrieving public ip address of instances")
    #Retrieving public ip address

    for ins in finst:
        if(ins[2]=='no'):
            #print("Instance Name: "+str(ins[1])+" Instance ID: "+str(ins[0])+" is a private instance.")
            data={
                'Instance Name ' : str(ins[1]),
                'IP ' : "Is a private instance",
                'Key Pair Name ' : str(ins[3])
                }
            json.dump(data,wfile)
            continue
        inst=ec2.Instance(ins[0])
        inst.wait_until_running()
        descinst=ec2client.describe_instances(
            InstanceIds=[
                    ins[0]
                ]
        )
        #print("Instance Name: "+str(ins[1])+" Instance ID: "+str(ins[0])+" is a public instance.")
        #print("Public IP: "+descinst['Reservations'][0]['Instances'][0]['PublicIpAddress'])
        data={
            'Instance Name ' : str(ins[1]),
            'IP ' : descinst['Reservations'][0]['Instances'][0]['PublicIpAddress'],
            'Key Pair Name ' : str(ins[3])
            }
        json.dump(data,wfile)

        '''
        while(1):
            if(ins[2]=='no'):
                print("Instance Name: "+str(ins[1])+" Instance ID: "+str(ins[0])+" is a private instance.")
                break;
            descinst=ec2client.describe_instances(
            InstanceIds=[
                    ins[0]
                    ]
            )
            if(descinst['Reservations'][0]['Instances'][0]['State']['Name']=="running"):
                print("Instance Name: "+str(ins[1])+" Instance ID: "+str(ins[0])+" is a public instance.")
                print("Public IP: "+descinst['Reservations'][0]['Instances'][0]['PublicIpAddress'])
                break
            time.sleep(10)
        '''

except ValueError as err:
    print(err)
fjson.close()
wfile.close()
