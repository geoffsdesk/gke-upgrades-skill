For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, but you should implement additional controls for production environments. Here's the recommended approach:

## Automatic Upgrade Behavior (Regular Channel)

- **Control plane**: Auto-upgrades within ~2-3 weeks of version availability
- **Node pools**: Auto-upgrade within ~2-3 weeks after control plane upgrade
- **Timing**: Upgrades occur during your configured maintenance window

## Recommended Production Strategy

### 1. **Configure Maintenance Windows**
```bash
# Set a maintenance window during low-traffic hours
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start="2023-01-01T02:00:00Z" \
    --maintenance-window-end="2023-01-01T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

### 2. **Enable Maintenance Exclusions** (for critical periods)
```bash
# Exclude upgrades during high-traffic events
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name="black-friday" \
    --add-maintenance-exclusion-start="2023-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="2023-11-27T23:59:59Z"
```

### 3. **Implement Staged Upgrades**
- Use **multiple clusters** (dev → staging → production)
- Configure different maintenance windows for each stage
- Consider using **node pool surge upgrades**:

```bash
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=1
```

### 4. **Monitor and Test**
```yaml
# Example monitoring setup
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  script.sh: |
    # Monitor cluster version
    kubectl version --short
    # Check node readiness
    kubectl get nodes
    # Verify workload health
    kubectl get pods --all-namespaces
```

## Best Practices

✅ **Keep automatic upgrades enabled** - Manual upgrades often lag behind security patches

✅ **Use notification channels** to monitor upgrade status
```bash
gcloud container clusters update CLUSTER_NAME \
    --notification-config=pubsub=projects/PROJECT_ID/topics/TOPIC_NAME
```

✅ **Test applications** against new Kubernetes versions in non-production first

✅ **Implement proper pod disruption budgets**:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-app
```

## When to Consider Manual Upgrades

Only override automatic upgrades if you need to:
- Upgrade immediately for security patches
- Coordinate with application deployments
- Test specific versions in staging environments

The Regular channel with proper maintenance windows and staged deployments provides the best balance of stability and security for production workloads.