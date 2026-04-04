Yes, there are several approaches to work around the quota constraint, depending on your platform and risk tolerance:

## Option 1: Manual Rolling Upgrade (Lowest Risk)
This bypasses surge capacity by manually managing the replacement process:

**For GKE:**
```bash
# Set max-surge to 0 and max-unavailable to 1 (or small number)
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --max-surge=0 \
    --max-unavailable=1

# Then proceed with upgrade
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE
```

**For EKS:**
```bash
# Update the node group with zero max_size increase
aws eks update-nodegroup-config \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name NODEGROUP_NAME \
    --update-config maxUnavailable=1
```

## Option 2: Temporary Resource Cleanup
Free up quota temporarily:
- Scale down non-critical workloads
- Delete unused node pools or instances
- Consider smaller instance types for the upgrade period

## Option 3: Multi-AZ Shuffle (If Applicable)
If quota is available in other AZs in the region:
1. Create new node pool in different AZ
2. Drain and migrate workloads
3. Delete old node pool
4. Recreate in original AZ with new version

## Option 4: In-Place Upgrade (Highest Risk)
Some platforms support in-place OS/runtime upgrades without node replacement, though this is less common and riskier.

## Recommended Approach:
Start with **Option 1** - it's the safest and most commonly supported. The upgrade will take longer but won't require additional quota.

What container platform are you using? I can provide more specific commands for your setup.