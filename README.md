# instavibe-bootstrap

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

This will build and deploy all the services to Google Cloud Run.
