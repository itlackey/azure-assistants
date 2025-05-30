import os
import json
import logging
import subprocess
from datetime import datetime
import sys
import time
import re
from dotenv import load_dotenv

from openai import OpenAI, AzureOpenAI

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Fetch the API configuration from environment variables
api_base_url = os.getenv("OPENAI_API_BASE_URL")
api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4o")

# Validate API settings
if not api_key:
    logging.error("API key is not set. Please set it in the .env file.")
    sys.exit(1)


def create_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_DEPLOYMENT")
    api_version = os.getenv("API_VERSION")

    if azure_endpoint:
        logging.info("Using Azure Open AI Endpoint...")
        return AzureOpenAI(
            api_version=api_version,
            azure_deployment=azure_deployment,
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=None,
            api_key=api_key,
        )
    else:
        return OpenAI(api_key=api_key)


client = create_openai_client()

# Directory to store all resource group folders
OUTPUT_DIR = "./output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# Function to read content from a text file
def read_text_file(file_path):
    with open(file_path, "r") as file:
        return file.read().strip()


# Load system message and user prompt from external files
system_message = read_text_file("resources/system_message.md")
user_prompt_template = read_text_file("resources/user_prompt.md")


# Function to extract tags from the ARM template's resources and format them as a dictionary
def extract_tags(template_content):
    tags_dict = {}

    resources = template_content.get("resources", [])
    for resource in resources:
        resource_tags = resource.get("tags", {})
        for key, value in resource_tags.items():
            tags_dict[key] = value

    return tags_dict


# Function to filter out specific resource types from the ARM template
def filter_resources(template_content):

    # TODO: Read this from a file, the file name should be able to be passed via a CLI arg or default to .types-exclude
    # Filter out specific resource types
    excluded_resource_types = [
        "Microsoft.DBforMySQL/flexibleServers/backups",
        "Microsoft.DBforMySQL/flexibleServers/backupsv2",
        "Microsoft.DBforMySQL/flexibleServers/configurations",
        "Microsoft.Web/sites/deployments",
        "Microsoft.OperationalInsights/workspaces/savedSearches",
        "Microsoft.OperationalInsights/workspaces/tables",
        "Microsoft.DataProtection/backupVaults/backupInstances",
        "microsoft.insights/scheduledqueryrules",
        "Microsoft.Compute/snapshots",
        "microsoft.insights/actionGroups",
        "Microsoft.Compute/sshPublicKeys",
        "Microsoft.CognitiveServices/accounts/raiPolicies",
        "Microsoft.CognitiveServices/accounts/defenderForAISettings",
        "Microsoft.CognitiveServices/accounts/deployments",
    ]

    # TODO: Read this from a file, the file name should be able to be passed via a CLI arg or default to .types-include
    # Only include these resource types, if any are listed
    included_resource_types = []

    ## Example of only summarizing CongnitiveServices
    # included_resource_types = [
    #     "Microsoft.CognitiveServices/accounts/raiPolicies",
    #     "Microsoft.CognitiveServices/accounts/defenderForAISettings",
    #     "Microsoft.CognitiveServices/accounts/deployments",
    # ]

    filtered_resources = [
        resource
        for resource in template_content.get("resources", [])
        if resource.get("type") not in excluded_resource_types
        and (
            len(included_resource_types) == 0
            or resource.get("type") in included_resource_types
        )
    ]

    # TODO: Remove the value of properties.publicKey for all resources of type "Microsoft.Compute/sshPublicKeys" to reduce token cost
    # TODO: Remove any values that may contain sensitive data
    # excluded_properties = []

    template_content["resources"] = filtered_resources
    return template_content


# Function to send the ARM template and parameters to OpenAI-compatible API and get the summary
def get_summary(template_file, resource_group_name, retry_count=1):

    with open(template_file, "r") as tf:
        template_content = json.load(tf)

    filtered_template_content = filter_resources(template_content)

    azure_tags = extract_tags(filtered_template_content)

    messages = [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": user_prompt_template.format(
                resource_group_name=resource_group_name,
                template_content=json.dumps(filtered_template_content),
            ),
        },
    ]

    # Retry mechanism for API call
    for attempt in range(retry_count):
        try:
            # Make the API call
            response = client.chat.completions.create(model=model, messages=messages)
            return response.choices[0].message.content, azure_tags
        except Exception as e:
            logging.error(f"Unexpected error occurred: {str(e)}")
            time.sleep(2**attempt)  # Exponential backoff

    logging.error(
        f"Failed to generate summary after {retry_count} attempts for resource group {resource_group_name}."
    )
    return None, None


# Function to generate front matter for markdown
def generate_front_matter(resource_group_name, azure_tags):
    title = f"Resource Group: {resource_group_name}"
    date = datetime.now().strftime("%Y-%m-%d")

    front_matter = "---\n"
    front_matter += f'title: "{title}"\n'
    front_matter += f"date: {date}\n"
    front_matter += "internal: true\n"

    front_matter += "azureTags:\n"
    for key, value in azure_tags.items():
        front_matter += f"  {key}: {value}\n"

    front_matter += "---\n\n"
    return front_matter


# Function to export ARM templates for a resource group
def export_template(resource_group_name, output_dir):
    rg_dir = os.path.join(output_dir, resource_group_name)
    os.makedirs(rg_dir, exist_ok=True)

    # Check if the template file already exists
    template_path = os.path.join(rg_dir, "template.json")
    if os.path.exists(template_path):
        logging.info(
            f"Template already exists for resource group: {resource_group_name}, skipping export."
        )
        return rg_dir  # Return the existing directory

    logging.info(f"Exporting ARM template for resource group: {resource_group_name}")

    export_command = [
        "az",
        "group",
        "export",
        "--name",
        resource_group_name,
        # "--include-parameter-default-value", # TODO: allow this to be an arg set via the CLI
        "--output",
        "json",
    ]

    try:
        with open(template_path, "w") as template_file:
            result = subprocess.run(
                export_command, stdout=template_file, stderr=subprocess.PIPE, text=True
            )

        if result.returncode != 0:
            logging.error(
                f"Failed to export template for resource group: {resource_group_name}. {result.stderr}"
            )
            return None
        else:
            logging.info(f"ARM template exported to {template_path}")
            return rg_dir
    except subprocess.CalledProcessError as e:
        logging.error(f"Error exporting ARM template for {resource_group_name}: {e}")
        return None


# Function to generate markdown summary for the resource group
def generate_markdown_for_resource_group(rg_dir, resource_group_name):
    template_file = os.path.join(rg_dir, "template.json")

    if not os.path.exists(template_file):
        logging.error(
            f"ARM template file not found for resource group: {resource_group_name}"
        )
        return

    logging.info(f"Generating summary for resource group: {resource_group_name}")

    summary, azure_tags = get_summary(template_file, resource_group_name)

    if azure_tags is None:
        logging.error(f"Failed to generate summary for {resource_group_name}")
        return

    front_matter = generate_front_matter(resource_group_name, azure_tags)

    markdown_file = os.path.join(rg_dir, f"{resource_group_name}.md")

    with open(markdown_file, "w") as md:
        md.write(front_matter)
        md.write(summary)
        md.write("\n\n**Note:** This document was generated using the Azure Assistants script and an LLM")

    logging.info(f"Markdown summary saved to {markdown_file}")


# Function to slugify a string to be used as a directory name
def slugify(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9-]", "-", value)
    value = re.sub(r"-+", "-", value)
    return value


# Function to get the current Azure subscription name
def get_subscription_name():
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "name", "-o", "tsv"],
            stdout=subprocess.PIPE,
            text=True,
        )
        subscription_name = result.stdout.strip()
        if not subscription_name:
            logging.error("Failed to get the Azure subscription name.")
            sys.exit(1)
        return subscription_name
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting Azure subscription name: {e}")
        sys.exit(1)


# Main function to process all resource groups
def process_all_resource_groups():
    try:
        subscription_name = get_subscription_name()
        slugified_subscription_name = slugify(subscription_name)
        output_dir = os.path.join(OUTPUT_DIR, slugified_subscription_name)
        os.makedirs(output_dir, exist_ok=True)

        result = subprocess.run(
            ["az", "group", "list", "--query", "[].name", "-o", "tsv"],
            stdout=subprocess.PIPE,
            text=True,
        )
        resource_groups = result.stdout.splitlines()

        if not resource_groups:
            logging.warning("No resource groups found.")
            return

        # TODO: Read this from a file, the file name should be able to be passed via a CLI arg or default to .rg-exclude
        # List of resource groups to exclude
        excluded_resource_groups = [
            "NetworkWatcherRG",
            "AzureBackupRG_centralus_1",
            "dashboards",
            "LogAnalyticsDefaultResources",
            "DefaultResourceGroup-CUS",
        ]

        # Filter out the excluded resource groups
        filtered_resource_groups = [
            rg for rg in resource_groups if rg not in excluded_resource_groups
        ]

        for rg in filtered_resource_groups:
            rg_dir = os.path.join(output_dir, rg)

            template_path = os.path.exists(os.path.join(rg_dir, "template.json"))
            markdown_path = os.path.exists(os.path.join(rg_dir, f"{rg}.md"))

            if template_path and markdown_path:
                logging.info(
                    f"Both template.json and {rg}.md already exist for resource group: {rg}, skipping."
                )
                continue

            rg_dir = export_template(rg, output_dir)
            if rg_dir:
                if not markdown_path:
                    generate_markdown_for_resource_group(rg_dir, rg)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error listing resource groups: {e}")
        sys.exit(1)


if __name__ == "__main__":
    process_all_resource_groups()
