# TPU Multislice Maintenance Impact & Preparation

## What will happen to your training job

**Critical reality: Your training will be completely interrupted.** Here's the cascading failure pattern for TPU multislice:

1. **Atomic slice recreation**: Each TPU slice (your 256-chip pods) gets recreated entirely in a single step — not rolling upgrades like CPU nodes
2. **Cascading restart**: When ANY slice in your multislice environment undergoes maintenance, ALL slices restart simultaneously
3. **Full job termination**: Your LLM training job will be killed and must restart from the last checkpoint

**Timeline expectations:**
- Maintenance event duration: ~30 minutes to 2 hours per slice
- Since all 4 slices restart together, expect 30min-2h total downtime
- If insufficient TPU capacity exists during recreation, the entire job blocks until hardware becomes available (could extend downtime significantly)

## Immediate preparation steps

### 1. Force checkpoint NOW
```bash
# If using JAX/Flax - trigger immediate checkpoint
# Send SIGUSR1 or your training framework's checkpoint signal
kubectl exec -n NAMESPACE POD_NAME -- kill -USR1 1

# Verify checkpoint completed successfully
kubectl logs -n NAMESPACE POD_NAME | grep -i checkpoint
```

### 2. Validate checkpoint integrity
```bash
# Check checkpoint files exist and are recent
gsutil ls -l gs://YOUR_CHECKPOINT_BUCKET/latest/
```

### 3. Apply maintenance exclusion (if you need more time)
```bash
# Block the maintenance for up to 30 days if you need to finish a critical training run
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "critical-training-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 4. Document current training state
```bash
# Capture current step, loss, model state
kubectl logs -n NAMESPACE POD_NAME --tail=100 > training-state-$(date +%Y%m%d).log

# Note: slice topology, batch size, learning rate schedule position
```

## Post-maintenance recovery plan

### 1. Verify slice topology integrity
```bash
# Check all TPU slices are healthy and properly networked
kubectl get pods -l app=YOUR_TRAINING_APP -o wide
kubectl describe tpumultislice YOUR_MULTISLICE_NAME

# Verify RDMA/interconnect between slices
kubectl exec -n NAMESPACE POD_NAME -- python -c "
import jax
print(f'JAX devices: {jax.device_count()}')
print(f'JAX hosts: {jax.host_count()}')
"
```

### 2. Resume training from checkpoint
```bash
# Your training resumption command here - example:
kubectl create job training-resume-$(date +%Y%m%d) --from=cronjob/training-job
# Or restart your existing training deployment
```

### 3. Monitor for topology/performance regression
- **First 1000 steps**: Watch for performance degradation vs pre-maintenance
- **FLOPS utilization**: Should match previous training efficiency
- **Cross-slice communication**: Monitor for increased latency between slices

## Multislice-specific risks

**Capacity dependency**: If Google doesn't have sufficient TPU v5e capacity during recreation, your slices will stay pending until hardware becomes available. This is beyond your control but can extend downtime from hours to potentially days in worst-case scenarios.

**Placement group preservation**: Verify your slices land in the same physical proximity post-maintenance. Poor placement can degrade inter-slice communication performance.

## Alternative: Proactive shutdown strategy

If the maintenance window conflicts with a critical training milestone:

1. **Checkpoint and gracefully stop training** before the maintenance window
2. **Scale your multislice to 0** temporarily
3. **Let maintenance complete on empty slices** (faster, no job interference)
4. **Scale back up and resume** when you're ready

```bash
# Scale down gracefully
kubectl scale deployment YOUR_TRAINING_DEPLOYMENT --replicas=0
# Wait for maintenance to complete
# Scale back up
kubectl scale deployment YOUR_TRAINING_DEPLOYMENT --replicas=1
```

This gives you control over the timing instead of letting the maintenance event interrupt mid-training.

**Bottom line**: Plan for a complete restart. The "maintenance event" for TPU multislice is effectively a reboot of your entire training infrastructure. Your checkpoint strategy is your lifeline.