#!/usr/bin/env python3

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

def run_az(command: list[str]) -> list[dict]:
    """Run an az CLI command and parse its JSON output."""
    print(f"Running command: {' '.join(['az'] + command)}")
    result = subprocess.run(["az"] + command + ["-o", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(['az'] + command)}")
        print(f"Error message: {result.stderr.strip()}")
        return []
    return json.loads(result.stdout)

def get_container_jobs(environment_name):
    """Fetch all container jobs for a given container app environment."""
    print(f"Fetching container jobs for environment: {environment_name}...")
    jobs = run_az(["containerapp", "job", "list", "--environment", environment_name])
    return jobs

def move_container_job(job, new_resource_group, new_environment):
    """Move a container job to a new resource group and environment."""
    print(f"Moving job {job['name']} to resource group {new_resource_group} and environment {new_environment}...")
    # Export the job configuration
    job_config = run_az(["containerapp", "job", "show", "--name", job["name"], "--resource-group", job["resourceGroup"]])

    # Update the resource group and environment in the configuration
    job_config["resourceGroup"] = new_resource_group
    job_config["environment"] = new_environment

    # # Delete the existing job
    # subprocess.run(["az", "containerapp", "job", "delete", "--name", job["name"], "--resource-group", job["resourceGroup"], "--yes"], check=True)

    # Create the job in the new resource group and environment
    subprocess.run(["az", "containerapp", "job", "create", "--name", job["name"], "--resource-group", new_resource_group, "--environment", new_environment, "--yaml", "-"], input=json.dumps(job_config), text=True, check=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Move container jobs to a new resource group and environment.")
    parser.add_argument("--source-environment", required=True, help="Source container app environment name.")
    parser.add_argument("--new-resource-group", required=True, help="New resource group name.")
    parser.add_argument("--new-environment", required=True, help="New container app environment name.")
    args = parser.parse_args()

    # Fetch all container jobs in the source environment
    jobs = get_container_jobs(args.source_environment)

    if not jobs:
        print(f"No container jobs found in environment: {args.source_environment}")
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