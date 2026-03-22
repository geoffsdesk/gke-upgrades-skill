### API Server Availability During Regional Upgrades

Because you are running a **regional** cluster, your control plane is highly available. GKE provisions multiple control plane replicas distributed across different zones in `us-central1`. 

During a control plane upgrade, **GKE performs a rolling update of these replicas**. One replica is taken offline, upgraded, and brought back online before moving to the next. 

**What this means for your team:**
*   **No complete API downtime:** Your API server remains available and continues to serve requests throughout the upgrade.
*   **Workloads are unaffected:** Running pods, services, and routing continue to function normally. The control plane upgrade does not restart your worker nodes.
*   **Minor disruptions to active sessions:** Long-running connections like `kubectl exec`, `kubectl port-forward`, or `kubectl logs` might drop if they are connected to a replica that restarts. They simply need to be reconnected.
*   **Controller/Operator resilience:** If you have custom operators, they might temporarily lose connection to the API server during a replica switch but will seamlessly reconnect (standard Kubernetes client-go behavior).

*Note: Since you are manually initiating this upgrade, it will bypass any configured maintenance windows and start immediately.*

---

### Phase 1: Pre-Upgrade Checklist

Before upgrading, verify that your cluster is ready for version 1.32.

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Region: us-central1 | Channel: Regular
- [ ] Check target version availability in the Regular channel: `gcloud container get-server-config --region us-central1 --format="yaml(channels)"`
- [ ] Check for deprecated API usage in 1.31 that will break in 1.32: Run `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated` or check the GKE deprecation insights dashboard in the Google Cloud Console.
- [ ] Review GKE release notes for breaking changes between 1.31 and 1.32.
- [ ] Verify third-party operators, controllers, and admission webhooks are compatible with 1.32.
```

---

### Phase 2: Control Plane Upgrade Runbook

Replace `CLUSTER_NAME` with your actual cluster name. Ensure you are authenticated and have the correct project selected.

#### 1. Pre-flight Checks
Find the exact `1.32` version available in the Regular channel:
```bash
# View available versions in the Regular channel
gcloud container get-server-config \
  --region us-central1 \
  --flatten="channels" \
  --filter="channels.channel=REGULAR" \
  --format="yaml(channels.validVersions)"

# Check current control plane version and health
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion)"

# Ensure all system pods are currently healthy
kubectl get pods -n kube-system | grep -v Running | grep -v Completed
```

#### 2. Execute the Control Plane Upgrade
Once you have identified the exact target version (e.g., `1.32.x-gke.x`), initiate the upgrade:
```bash
# Upgrade the control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version TARGET_VERSION
```
*Note: This operation typically takes 15–30 minutes for a regional cluster.*

#### 3. Post-Upgrade Validation
Verify the upgrade was successful:
```bash
# Check the new control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify the API server is responding correctly
kubectl cluster-info
kubectl get nodes

# Check system pod health
kubectl get pods -n kube-system
```

### Next Steps: Node Pools
Once your control plane is successfully running 1.32, your node pools will remain on 1.31. GKE allows nodes to be up to two minor versions behind the control plane (so 1.31 nodes with a 1.32 control plane is fully supported). 

However, because you are enrolled in the **Regular release channel**, GKE will eventually auto-upgrade your node pools to match the control plane based on your configured maintenance windows. 

If you want to manually upgrade your node pools immediately following the control plane upgrade, let me know and I can provide the runbook and strategy recommendations (Surge vs. Blue-Green) for your worker nodes!