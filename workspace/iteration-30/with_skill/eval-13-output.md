# GKE Upgrade Plan for Long-Running Batch Jobs

For your 8-16 hour batch jobs, GKE's default surge upgrade strategy will **force-evict jobs after 1 hour** — far shorter than your job duration. Here's how to handle this upgrade safely:

## Recommended Strategy: Autoscaled Blue-Green

**Use GKE's autoscaled blue-green upgrade strategy** — it's specifically designed for long-running workloads like yours:

```bash
# Configure autoscaled blue-green for your batch node pool
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Key advantages:**
- **Respects long termination periods** — no 1-hour force-eviction limit like surge upgrades
- **Cost-efficient** — scales down old nodes as jobs drain to new nodes (unlike standard blue-green which doubles capacity)
- **Graceful transition** — jobs complete naturally before nodes are removed

## Upgrade Execution Plan

### 1. Pre-Upgrade Preparation

```bash
# Set maintenance exclusion to prevent auto-upgrades during active batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-freeze" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-end-time "YYYY-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 2. Batch Job Configuration

Update your batch job specs to handle graceful termination:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for cleanup
      containers:
      - name: batch-processor
        image: your-image
        # Add annotation to prevent forced eviction
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
```

### 3. Sequential Upgrade Steps

**Step 1: Control Plane Upgrade**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX
```

**Step 2: Wait for Job Completion Window**
- Monitor running jobs: `kubectl get jobs -A --field-selector status.active>0`
- Coordinate with batch job schedulers to pause new submissions
- Wait for current 8-16h jobs to complete naturally

**Step 3: Node Pool Upgrade**
```bash
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX
```

## Alternative: Maintenance Exclusion Strategy

If you prefer maximum control over timing:

```bash
# Block all node upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Workflow:**
1. Run batch campaigns with nodes frozen at 1.30
2. During planned maintenance windows (between campaigns), manually trigger upgrades
3. Remove exclusion temporarily, upgrade, then re-apply for next campaign

## Validation Checklist

```markdown
- [ ] Autoscaled blue-green strategy configured on batch node pools
- [ ] terminationGracePeriodSeconds set to 3600s on batch jobs
- [ ] safe-to-evict annotation added to long-running jobs
- [ ] Batch job scheduler paused during upgrade window
- [ ] No active jobs running before starting node pool upgrade
- [ ] Checkpoint/resume capability verified for batch jobs
- [ ] Monitoring in place to track job completion rates
```

## Risk Mitigation

- **Checkpointing**: Ensure your batch jobs support checkpointing so they can resume from interruption
- **Job Queue Management**: Coordinate with your batch scheduler (Kubernetes Jobs, Airflow, etc.) to pause new submissions
- **Staging Validation**: Test the 1.31 upgrade on a dev cluster with representative batch workloads first

This approach protects your long-running jobs while keeping your cluster on a supported, secure version. The autoscaled blue-green strategy is specifically designed for workloads like yours that can't tolerate the 1-hour eviction timeout of standard surge upgrades.