This is a recoverable situation, but you need to act carefully since you have a mixed-version cluster. Here's your action plan:

## Immediate Assessment
First, check the current state:
```bash
kubectl get nodes -o wide
kubectl get pods --all-namespaces -o wide
```

Look for:
- Which nodes are on 1.32 vs older versions
- Any pods stuck in pending/failed states
- Workload distribution across old/new nodes

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
1. **Check the specific error**:
   ```bash
   # For GKE
   gcloud container operations list
   gcloud container operations describe [OPERATION-ID]
   
   # For EKS  
   aws eks describe-update --cluster-name [CLUSTER] --update-id [UPDATE-ID]
   ```

2. **Address the root cause** (common issues):
   - Insufficient capacity/quotas
   - PodDisruptionBudgets blocking drainage
   - Pods without proper resource requests
   - Custom admission controllers blocking system pods

3. **Retry the upgrade**:
   ```bash
   # GKE
   gcloud container clusters upgrade [CLUSTER-NAME] --node-pool=[POOL-NAME]
   
   # EKS
   aws eks update-nodegroup-version --cluster-name [CLUSTER] --nodegroup-name [POOL]
   ```

### Option 2: Manual Completion
If the automated retry fails:

1. **Cordon remaining old nodes**:
   ```bash
   kubectl cordon [OLD-NODE-NAME]
   ```

2. **Drain nodes one by one**:
   ```bash
   kubectl drain [NODE-NAME] --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
   ```

3. **Replace nodes manually** through your cloud provider console

## Critical Considerations

**Pod Disruption**: Check your PDBs and ensure they allow the upgrade:
```bash
kubectl get pdb --all-namespaces
```

**Version Skew**: You're currently violating version skew policies. Kubernetes only supports nodes up to 2 minor versions behind the control plane, so complete this upgrade ASAP.

**Workload Scheduling**: Ensure critical workloads can schedule on the upgraded nodes:
```bash
kubectl get pods -o wide | grep [OLD-NODE-NAME]
```

## Next Steps After Recovery
1. Complete the remaining node pools immediately
2. Monitor cluster health throughout
3. Consider implementing blue-green node pool upgrades for future updates

What specific error message did you see when the upgrade failed? That will help determine the best recovery approach.