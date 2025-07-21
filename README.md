# instavibe-bootstrap

## Prerequisites

Before you begin, ensure you have the following installed:

*   [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)

## Deployment

To deploy all the services, first create a `.env` file in the root of the project. You can copy the `.env.example` file to get started:

```bash
cp .env.example .env
```

Then, fill in the values in your `.env` file.

Finally, run the following command:

```bash
python deploy.py
```

This will build the Docker images using Google Cloud Build and then deploy them to Google Cloud Run. After the deployment is complete, the script will print the URLs of the deployed services.

The script will also automatically configure the services to communicate with each other by setting the required environment variables.
