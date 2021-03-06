from __future__ import print_function

import re
import time

from botocore.exceptions import ClientError

from . import aws, config, errors, ssh


def _send_command(instance_ids):

    document_name = config.get('ssm.document.name')
    parameters = config.get('ssm.parameters')

    print('[ssha] ssm send {document} to {instances}'.format(
        document=document_name,
        instances=' and '.join(instance_ids),
    ))

    ssm = aws.client('ssm')

    result = ssm.send_command(
        InstanceIds=instance_ids,
        DocumentName=document_name,
        Parameters=parameters,
    )

    try:
        command_id = result['Command']['CommandId']
    except Exception:
        errors.json_exit(result)

    return command_id


def _wait_for_command(instance_ids, command_id):

    ssm = aws.client('ssm')

    outputs = {}

    for instance_id in instance_ids:

        result = {'Status': 'Pending'}

        while result['Status'] in ('Pending', 'InProgress', 'Delayed'):
            time.sleep(0.25)
            try:
                result = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )
            except ClientError:
                pass

        if result['Status'] != 'Success':
            errors.json_exit(result)

        print('[ssha] ssm command finished on {}'.format(instance_id))
        outputs[instance_id] = result['StandardOutputContent']

    return outputs


def find_instances():

    ssm = aws.client('ssm')

    response = ssm.describe_instance_information()
    if response['ResponseMetadata']['HTTPStatusCode'] != 200:
        errors.json_exit(response)

    return response['InstanceInformationList']


def send_command(*instances):

    instances = [instance for instance in instances if instance]
    instance_ids = [instance['InstanceId'] for instance in instances]

    command_id = _send_command(
        instance_ids=instance_ids,
    )

    outputs = _wait_for_command(
        instance_ids=instance_ids,
        command_id=command_id,
    )

    host_keys_file = config.get('ssm.host_keys_file')
    if host_keys_file:
        with open(host_keys_file, 'w') as open_file:
            for instance in instances:
                hostname = ssh.get_hostname(instance)
                instance_id = instance['InstanceId']
                host_keys = outputs[instance_id]
                for line in host_keys.splitlines():
                    # Replace hostname from the host keys line
                    # with the instance's hostname.
                    line = re.sub(r'^[^#\s]+', hostname, line)
                    open_file.write(line + '\n')
