# HERA Dashboard Server

A quick setup to create a VM running in the Google Cloud that runs SSH and
HTTP.


## Creation

1. Install the `gcloud` command line client.
2. Create a new Google Cloud Platform project.
3. Enable Google Compute Engine for the project, which requires enabling
   billing.
4. Get name of latest container-OS image:
   ```
   gcloud compute images list --project cos-cloud --no-standard-images
   ```
4. Create server:
   ```
   gcloud compute instances create server \
     --zone us-east1-d \
     --machine-type f1-micro \
     --metadata-from-file user-data=cloud-config.yaml \
     --image-project cos-cloud \
     --image IMAGE_NAME
   ```
5. Allow HTTP connections to server:
   ```
   gcloud compute firewall-rules create default-allow-http \
     --network default \
     --action allow \
     --direction ingress \
     --rules tcp:80
   ```
   Note that outgoing connections must be allowed so that the instance can
   pull down Docker images; it looks like other bits of the Google
   infrastructure probably want outgoing connections too.


## Maintenance

To log in, this should suffice if the active project is configured correctly:

```
gcloud compute ssh server
```
