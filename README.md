# Azure Assistants

This repository provides tools for generating Markdown documentation for Azure Resource Groups using ARM (Azure Resource Manager) templates. It includes scripts and configuration files that integrate with OpenAI or Azure OpenAI to create comprehensive, human-readable summaries of the resources in the templates.

## Repository Contents

### Environment Configuration

- **`.env.example`**: Example configuration file for setting up environment variables required by the scripts. This file should by copied to `.env` and one of the three configurations should be filled in with the correct API endpoint settings for your environment.

    ```plaintext
    # Use Azure OpenAI endpoint
    AZURE_OPENAI_ENDPOINT=https://<your endpoint name>.openai.azure.com
    AZURE_DEPLOYMENT=<deployment name>
    API_VERSION="<deployment version>"
    OPENAI_API_KEY=""
    OPENAI_MODEL="<deployment model name>"

    # Use the OpenAI endpoint
    OPENAI_API_BASE_URL=https://api.openai.com/v1
    OPENAI_API_KEY=your-openai-api-key
    OPENAI_MODEL=gpt-3.5-turbo

    # Use local Ollama endpoint
    OPENAI_API_BASE_URL=http://localhost:11434
    OPENAI_API_KEY=requires_any_value
    OPENAI_MODEL=llama3.2
    ```

### Scripts

- **`document_resource_groups.py`**: Main script for exporting ARM templates for resource groups and generating markdown documentation. The script retrieves resource groups, exports their ARM templates, and interacts with OpenAI to summarize the templates. It can be run with:
    ```bash
    python document_resource_groups.py
    ```

### Templates

- **`system_message.md`**: Provides the system message for OpenAI, setting context about the role and purpose of the documentation being generated.
- **`user_prompt.md`**: Template for the user prompt sent to OpenAI, including sections for resource group details, data storage, networking, security overview, and other information.

### Dependencies

- **`requirements.txt`**: Specifies Python dependencies for the project.
    ```plaintext
    openai
    python-dotenv
    ```

## Getting Started

### Prerequisites

Ensure you have Python installed on your machine. You will also need access to the Azure CLI for exporting ARM templates and connecting to your subscription. Once these tools are installed, follow these steps to run the documentation script on your resource groups.

### Installation

1. Clone the repository to your local machine.
    ```bash
    git clone <repository-url>
    ```
2. Navigate to the project directory and install the required Python packages.
    ```bash
    cd <project-directory>
    python -m venv .venv
    source activate/.venv/bin/activate
    pip install -r requirements.txt
    ```
3. Copy `.env.example` to `.env` and fill in the required environment variables.
    ```bash
    cp .env.example .env
    ```

### Usage

1. Log into the subscript you would like to document:
    ```bash
    az login
    az account set -s "subscription name"
    ```
1. To generate markdown documentation for resource groups, run the main script:
    ```bash
    python document_resource_groups.py
    ```

## Troubleshooting

- **API Key Error**: Ensure your API key is set correctly in the `.env` file.
- **Azure CLI Issues**: Make sure you are logged in to the Azure CLI and have the necessary permissions to list and export resource groups.

## Contributing

Feel free to submit issues or pull requests if you have any improvements or additions.

