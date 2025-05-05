#!/usr/bin/env python3

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

def run_az(command: list[str]) -> list[dict]:
    """Run an az CLI command and parse its JSON output."""
    print(f"Running command: {' '.join(['az'] + command)}")

    if command[2] == "create":
        return
    
    result = subprocess.run(["az"] + command + ["-o", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(['az'] + command)}")
        print(f"Error message: {result.stderr.strip()}")
        return []
    
    return json.loads(result.stdout)

def get_container_jobs(resource_group):
    """Fetch all container jobs for a given resource group."""
    print(f"Fetching container jobs for resource group: {resource_group}...")
    jobs = run_az(["containerapp", "job", "list", "-g", resource_group])
    return jobs

def move_container_job(job, new_resource_group, new_environment):
    """Move a container job to a new resource group and environment."""
    print(f"Moving job {job['name']} to resource group {new_resource_group} and environment {new_environment}...")
    # Export the job configuration
    job_config = run_az(["containerapp", "job", "show", "--name", job["name"], "--resource-group", job["resourceGroup"]])
    #print(json.dumps(job_config))
    
    # Update the resource group and environment in the configuration
    job_config["resourceGroup"] = new_resource_group
    subscription_id = job_config['id'].split('/')[2]
    job_config["id"] = f"/subscriptions/{subscription_id}/resourceGroups/{new_resource_group}/providers/Microsoft.App/jobs/{job['name']}"
    job_config["properties"]["environmentId"] = f"/subscriptions/{subscription_id}/resourceGroups/{new_resource_group}/providers/Microsoft.App/managedEnvironments/{new_environment}"
    job_config["properties"]["eventStreamEndpoint"] = f"https://centralus.azurecontainerapps.dev/subscriptions/{subscription_id}/resourceGroups/{new_resource_group}/containerApps/{job['name']}/eventstream"

    # Update the userAssignedIdentities in the job configuration
    job_config["identity"]["userAssignedIdentities"] = {
        f"/subscriptions/{subscription_id}/resourcegroups/{new_resource_group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/databasin-env-job-uami": {
            "clientId": "1a8af676-a3a0-4b64-89c2-430be47a6954",
            "principalId": "f75db1a1-282a-4c6f-bf99-1b20405e3f4e"
        }
    }

    # Update the image in the job configuration
    for container in job_config["properties"]["template"]["containers"]:
        if container["image"]:
            container["image"] = "databasin.azurecr.io/databasin-job:1.0.0-RELEASE"

    # # Delete the existing job
    # subprocess.run(["az", "containerapp", "job", "delete", "--name", job["name"], "--resource-group", job["resourceGroup"], "--yes"], check=True)

    print(f"Creating job {job['name']} in resource group {new_resource_group} and environment {new_environment}...")
    print(json.dumps(job_config))

    # Create the job in the new resource group and environment
    subprocess.run(["az", "containerapp", "job", "create", "--name", job["name"], "--resource-group", new_resource_group, "--environment", new_environment, "--yaml", "-"], input=json.dumps(job_config), text=True, check=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Move container jobs to a new resource group and environment.")
    parser.add_argument("--source-resource-group", required=True, help="Source resource group name.")
    parser.add_argument("--new-resource-group", required=True, help="New resource group name.")
    parser.add_argument("--new-environment", required=True, help="New container app environment name.")
    args = parser.parse_args()

    # Fetch all container jobs in the source resource group
    jobs = get_container_jobs(args.source_resource_group)

    if not jobs:
        print(f"No container jobs found in resource group: {args.source_resource_group}")
        return

    # Move each job to the new resource group and environment
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(move_container_job, job, args.new_resource_group, args.new_environment)
            for job in jobs
        ]
        for future in futures:
            future.result()

    print("All container jobs have been moved successfully.")

if __name__ == "__main__":
    main()