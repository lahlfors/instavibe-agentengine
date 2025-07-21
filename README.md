# instavibe-bootstrap

## Deployment

To deploy all the services, run the following command:

```bash
python deploy.py
```

This will build and deploy all the services to Google Cloud Run. Make sure you have set the `PROJECT_ID` and `REGION` environment variables. You can do this by sourcing the `set_env.sh` script:

```bash
source set_env.sh
```
