Yes, you can proceed with the upgrade using a **drain-first strategy** that doesn't require any surge nodes. Here are your options:

## Option 1: Switch to drain-first mode (recommended)

This creates no extra nodes — it drains the old node before creating the replacement:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Trade-off:** Temporary capacity loss (one node at a time is unavailable), but zero extra quota needed. Good for most workloads that can tolerate brief capacity reduction.

## Option 2: Minimal surge with reduced parallelism

If you have quota for just 1 extra node:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This creates only 1 surge node at a time — much slower but fits minimal extra quota.

## Option 3: Free up quota temporarily

Scale down non-critical workloads during the upgrade window:

```bash
# Scale down dev/test deployments
kubectl scale deployment DEV_DEPLOYMENT --replicas=0 -n DEV_NAMESPACE
kubectl scale deployment CANARY_DEPLOYMENT --replicas=0 -n PROD_NAMESPACE

# Proceed with original surge settings
# Scale back up after upgrade completes
```

## Option 4: Off-peak timing optimization

Schedule the upgrade during off-peak hours (nights/weekends) when cluster autoscaler has scaled down other workloads, freeing quota naturally.

## Recommendation

**Use Option 1 (drain-first) if your workloads can tolerate temporary capacity loss.** This is the cleanest solution — no quota dependency, and the upgrade completes successfully. The capacity dip is brief (only while nodes are being replaced).

**Combine with Option 3** if you want to minimize the capacity impact — scale down 2-3 non-critical deployments AND use drain-first mode for maximum safety.

Once you apply the new surge settings, the stuck upgrade should resume automatically within a few minutes. Monitor with:

```bash
watch 'kubectl get nodes -o wide'
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```

Would you like me to help you identify which non-critical workloads could be temporarily scaled down?