Here are your options to upgrade without needing additional GPU quota for surge nodes:

## 1. **Blue-Green Deployment Strategy**
- Create a new node pool with the updated configuration
- Gradually drain and migrate workloads to the new pool
- Delete the old pool once migration is complete
- **Pros**: Zero downtime, full control over migration
- **Cons**: Requires careful workload orchestration

## 2. **Reduce Max Surge Setting**
```yaml
# Set surge to 0 and max unavailable to a small number
upgradeSettings:
  maxSurge: 0
  maxUnavailable: 1  # or 2-4 depending on your tolerance
```
- This upgrades nodes in-place without requiring additional capacity
- **Pros**: No extra quota needed
- **Cons**: Temporary reduction in available capacity during upgrade

## 3. **Staged Upgrade with Node Pool Splitting**
- Temporarily split your pool into smaller chunks
- Upgrade each chunk separately with lower surge requirements
- **Pros**: More granular control, reduced blast radius
- **Cons**: More complex orchestration

## 4. **Manual Node Cordoning and Draining**
```bash
# Manually control the upgrade process
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
# Upgrade individual nodes through GCP console/CLI
kubectl uncordon <node-name>
```

## 5. **Request Temporary Quota Increase**
- Contact Google Cloud support for temporary H100 quota bump
- Usually processed within hours for existing customers
- **Pros**: Maintains standard upgrade process
- **Cons**: Requires support interaction

Given the size of your deployment (64 A3-mega nodes), I'd recommend **option 2** (reducing max surge) as the quickest path forward, combined with careful monitoring of your workload tolerance for temporary capacity reduction.

Which approach aligns best with your downtime tolerance and operational constraints?