Yes, you have several options to work around the quota constraint and proceed with your node pool upgrade:

## Immediate Solutions

### 1. **Reduce Surge Configuration**
Temporarily lower the surge settings to minimize additional nodes needed:

```bash
# For GKE
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --max-surge=1 \
  --max-unavailable=0

# For EKS (update the launch template)
aws eks update-nodegroup-config \
  --cluster-name CLUSTER_NAME \
  --nodegroup-name POOL_NAME \
  --update-config maxUnavailable=0,maxUnavailablePercentage=10
```

### 2. **Scale Down Non-Critical Workloads**
Free up compute resources temporarily:

```bash
# Scale down deployments
kubectl scale deployment non-critical-app --replicas=0

# Or use node affinity to consolidate workloads
kubectl patch deployment app-name -p '{"spec":{"template":{"spec":{"nodeSelector":{"upgrade-group":"keep"}}}}}'
```

### 3. **Manual Rolling Upgrade Approach**
Perform a controlled, node-by-node upgrade:

```bash
# Drain nodes manually one at a time
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete the drained node (cloud provider will replace it with upgraded version)
kubectl delete node NODE_NAME

# Wait for replacement node to join and become ready
kubectl get nodes -w

# Repeat for next node
```

### 4. **Use Different Instance Types/Zones**
If quota is type-specific:

```bash
# Create a temporary node pool with different instance types
gcloud container node-pools create temp-upgrade-pool \
  --cluster=CLUSTER_NAME \
  --machine-type=e2-standard-2 \  # Different type
  --zone=different-zone \
  --num-nodes=2

# Migrate workloads, then upgrade original pool
```

## Recommended Approach

I'd suggest the **manual rolling upgrade** approach as it's most reliable:

```bash
#!/bin/bash
# Safe manual upgrade script

NODES=$(kubectl get nodes -l node-pool=your-pool -o name)

for node in $NODES; do
  echo "Upgrading $node..."
  
  # Drain the node
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=300s
  
  # Delete node (triggers replacement)
  kubectl delete $node
  
  # Wait for replacement
  echo "Waiting for replacement node..."
  sleep 120
  
  # Wait for cluster to stabilize
  kubectl wait --for=condition=Ready nodes --all --timeout=600s
  
  echo "$node upgrade complete"
done
```

This approach requires zero additional quota since you're replacing nodes one-for-one rather than creating surge capacity.

Would you like me to help you implement any of these approaches for your specific cloud provider?