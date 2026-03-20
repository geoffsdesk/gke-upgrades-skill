# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Complete Training Interruption**: Your LLM training will be fully interrupted. TPU multislice environments have fundamentally different maintenance behavior than regular GPU clusters:

### Atomic Recreation
- Each TPU slice (256 chips) is recreated entirely in a single step — not rolling upgrades like CPU/GPU nodes
- All pods on each slice restart simultaneously, losing any in-memory state

### Cascading Restart (Critical Detail)
- **Any maintenance event on ANY of your 4 slices triggers restart of ALL slices**
- This means if GKE touches just one slice, your entire 1,024-chip training environment goes down
- The "blast radius" is your complete multislice setup, not individual slices

### Capacity-Dependent Downtime
- GKE must recreate all slices with fresh TPU hardware allocation
- If insufficient TPU v5e capacity exists in your zone during recreation, slices will block until hardware becomes available
- Downtime could range from 15-30 minutes (best case) to several hours if capacity is constrained

## Preparation Checklist

```
TPU Multislice Maintenance Prep
- [ ] Checkpoint saved at latest training step
- [ ] Verify checkpoint integrity and resumability  
- [ ] Training script handles checkpoint resume correctly
- [ ] Maintenance window timing confirmed with GKE
- [ ] Stakeholders notified of complete training interruption
- [ ] Post-maintenance validation plan ready
```

## Pre-Maintenance Actions

### 1. Force Checkpoint Save
```bash
# If your trainer supports SIGTERM handling for checkpointing
kubectl exec -n NAMESPACE POD_NAME -- kill -TERM 1

# Or trigger checkpoint via your training framework's API/signal mechanism
# Verify checkpoint written to persistent storage (GCS bucket, etc.)
```

### 2. Graceful Training Pause
```bash
# Stop training job cleanly BEFORE maintenance window
kubectl scale deployment TRAINING_DEPLOYMENT --replicas=0 -n NAMESPACE

# Or if using Jobs/StatefulSets, delete pods to trigger clean shutdown
kubectl delete pods -l app=llm-training -n NAMESPACE --grace-period=300
```

### 3. Verify Training State
```bash
# Confirm latest checkpoint is complete and accessible
gsutil ls -l gs://YOUR_BUCKET/checkpoints/
# Test checkpoint loading in a small validation run if possible
```

## During Maintenance

**Hands-off Period**: Once maintenance begins, all 4 slices will be recreated. You cannot influence the process or speed it up. Monitor via:

```bash
# Check slice recreation status
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_TPU_POOL

# Monitor pod status during recreation
kubectl get pods -n NAMESPACE -w
```

## Post-Maintenance Recovery

### 1. Validate Slice Availability
```bash
# Confirm all 1,024 chips available
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_TPU_POOL
# Should show 4 nodes (slices) in Ready state

# Check TPU topology is correct
kubectl describe nodes | grep -A 5 "cloud.google.com/gke-accelerator"
```

### 2. Resume Training
```bash
# Restart training with checkpoint resume
kubectl apply -f llm-training-job.yaml

# Monitor training restart
kubectl logs -f -n NAMESPACE TRAINING_POD_NAME
```

### 3. Verify Training Health
- Confirm checkpoint loaded successfully
- Validate loss curves continue from pre-maintenance levels
- Check training throughput (tokens/second) matches pre-maintenance baseline
- Monitor for any TPU communication errors between slices

## Timeline Expectations

| Phase | Duration | Notes |
|-------|----------|-------|
| **Preparation** | 30-60 minutes | Checkpoint save + graceful shutdown |
| **Slice Recreation** | 15-120+ minutes | Depends on TPU v5e availability in zone |
| **Pod Restart** | 5-15 minutes | Framework initialization across 1,024 chips |
| **Training Resume** | 5-10 minutes | Checkpoint loading + validation |

**Total Downtime**: Budget 1-3 hours minimum. In worst-case capacity scenarios, could extend to 4+ hours.

## Specific TPU v5e Considerations

- **Zone capacity**: TPU v5e has limited availability. If other customers are also recreating slices, capacity contention increases downtime
- **Slice locality**: Your 4 slices need to be co-located for optimal interconnect. Recreation may place them suboptimally, affecting training performance
- **Driver compatibility**: Maintenance may update the TPU runtime version, potentially requiring changes to your training framework (JAX/PyTorch versions)

## Risk Mitigation

### Before Maintenance
- **Extended checkpoint frequency**: Increase checkpoint saves in the days before maintenance
- **Backup strategy**: Ensure checkpoints are replicated across regions
- **Capacity reservation**: If available, consider TPU reservations to guarantee post-maintenance capacity

### For Future Training
- **Fault-tolerant design**: Implement preemption-resistant training that can handle arbitrary TPU slice failures
- **Maintenance exclusions**: Use GKE maintenance exclusions during critical training phases:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "critical-training-phase" \
  --add-maintenance-exclusion-start-time $(date -d "today" --iso-8601) \
  --add-maintenance-exclusion-end-time $(date -d "+30 days" --iso-8601) \
  --add-maintenance-exclusion-scope no_upgrades
```

The key insight: TPU multislice maintenance is fundamentally different from standard Kubernetes upgrades. Your entire 1,024-chip environment is treated as a single atomic unit that gets completely recreated. Plan for full interruption, not rolling updates.