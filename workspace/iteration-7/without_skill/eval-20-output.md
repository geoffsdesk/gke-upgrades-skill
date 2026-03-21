# GKE Cluster Upgrade Runbook: 1.32 to 1.32

I notice you mentioned upgrading from 1.32 to 1.32, which would be the same version. I'll assume you meant upgrading **to** 1.32 from an earlier version. Here's a complete step-by-step runbook.

## Prerequisites

- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Cluster admin permissions
- Maintenance window scheduled (upgrades can take 30-60 minutes)

## Step 1: Initial Assessment and Preparation

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Authenticate and Set Context
```bash
# Authenticate with GCP
gcloud auth login

# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID
```

### 1.3 Verify Current Cluster State
```bash
# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 1.4 Check Available Versions
```bash
# See available versions for Regular channel
gcloud container get-server-config --zone $ZONE --format="yaml(channels)"
```

## Step 2: Pre-Upgrade Checks

### 2.1 Backup Critical Data
```bash
# Export important configurations (adjust namespaces as needed)
kubectl get all --all-namespaces -o yaml > cluster-backup-$(date +%Y%m%d-%H%M%S).yaml

# Export persistent volume claims
kubectl get pvc --all-namespaces -o yaml > pvc-backup-$(date +%Y%m%d-%H%M%S).yaml
```

### 2.2 Check Pod Disruption Budgets
```bash
kubectl get pdb --all-namespaces
```

### 2.3 Verify Application Health
```bash
# Check deployment status
kubectl get deployments --all-namespaces

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
```

## Step 3: Control Plane Upgrade

### 3.1 Upgrade Master/Control Plane
```bash
# Start control plane upgrade to 1.32
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --master --cluster-version=1.32-gke.latest

# Monitor upgrade progress
gcloud container operations list --zone $ZONE
```

### 3.2 Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete (this can take 10-20 minutes)
# Check the master version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Verify kubectl connectivity
kubectl version
kubectl get nodes
```

## Step 4: Node Pool Upgrades

### 4.1 Upgrade default-pool
```bash
# Upgrade default-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=default-pool

# Monitor the upgrade
kubectl get nodes -w
```

### 4.2 Monitor default-pool Upgrade
```bash
# Check node versions during upgrade
kubectl get nodes -o wide

# Monitor pod rescheduling
kubectl get pods --all-namespaces -o wide | grep default-pool
```

### 4.3 Upgrade workload-pool
```bash
# Upgrade workload-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=workload-pool

# Monitor the upgrade
kubectl get nodes -w
```

### 4.4 Monitor workload-pool Upgrade
```bash
# Check node versions during upgrade
kubectl get nodes -o wide

# Monitor pod rescheduling
kubectl get pods --all-namespaces -o wide | grep workload-pool
```

## Step 5: Post-Upgrade Verification

### 5.1 Verify All Components
```bash
# Check final cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Check all node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Verify all node pools
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE
```

### 5.2 Application Health Check
```bash
# Check all pods are running
kubectl get pods --all-namespaces

# Check deployments
kubectl get deployments --all-namespaces

# Check services
kubectl get services --all-namespaces

# Check ingress (if applicable)
kubectl get ingress --all-namespaces
```

### 5.3 Detailed Health Verification
```bash
# Check node conditions
kubectl describe nodes | grep -A 10 "Conditions:"

# Check cluster events for any errors
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20

# Verify DNS is working
kubectl run test-dns --image=busybox --rm -it -- nslookup kubernetes.default.svc.cluster.local
```

## Step 6: Cleanup and Documentation

### 6.1 Clean Up Test Resources
```bash
# Remove any test pods if they weren't auto-removed
kubectl delete pod test-dns 2>/dev/null || true
```

### 6.2 Final Status Report
```bash
echo "=== UPGRADE COMPLETE ==="
echo "Cluster: $CLUSTER_NAME"
echo "Zone: $ZONE"
echo "Master Version:"
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"
echo "Node Versions:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion --no-headers
echo "Node Pools:"
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE --format="table(name,version,status)"
```

## Troubleshooting Common Issues

### If upgrade fails:
```bash
# Check operation status
gcloud container operations list --zone $ZONE

# Get operation details
gcloud container operations describe OPERATION_ID --zone $ZONE

# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status,statusMessage)"
```

### If nodes are stuck:
```bash
# Check node conditions
kubectl describe node NODE_NAME

# Check node events
kubectl get events --field-selector involvedObject.name=NODE_NAME
```

### If pods won't reschedule:
```bash
# Check pod events
kubectl describe pod POD_NAME -n NAMESPACE

# Check for resource constraints
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Important Notes

1. **Timing**: Each upgrade phase can take 15-45 minutes
2. **Disruption**: Node upgrades will reschedule pods, causing temporary disruption
3. **Rollback**: Control plane upgrades cannot be rolled back
4. **Monitoring**: Keep monitoring applications throughout the process
5. **Support**: Keep this runbook and all output for troubleshooting

## Emergency Contacts

- Document your team's escalation path
- Have GCP support contact information ready
- Ensure multiple team members can execute this runbook

---

**Total Expected Duration: 1-2 hours**

**Risk Level: Medium** (Standard cluster upgrades are well-tested, but always carry some risk)

This runbook assumes a straightforward upgrade. If you encounter issues or have specific application requirements, consult with your platform team or GCP support.