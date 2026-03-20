# GKE Mixed AI/ML Fleet Upgrade Plan (v1.29 → v1.30)

## Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability while minimizing disruption to your 5,000-node AI/ML platform.

## Pre-Upgrade Preparation (Week -2 to -1)

### Phase 0: Assessment & Preparation
- **Control plane upgrade** (minimal downtime)
- **Backup critical workloads and configurations**
- **Test upgrade on development cluster**
- **Prepare rollback procedures**
- **Coordinate with ML teams on training schedules**

## Phased Upgrade Strategy

### Phase 1: Development Environment (Days 1-2)
**Target: 500 T4 nodes**
- **Priority**: Lowest impact, testing ground
- **Strategy**: Blue-green deployment with temporary node pool
- **Duration**: 4-6 hours per batch of 100 nodes
- **Validation**: Run comprehensive ML workload tests

```yaml
# Development Node Pool Upgrade
Batch Size: 100 nodes
Surge Settings: max-surge=50, max-unavailable=0
Schedule: Off-peak hours (weekends preferred)
```

### Phase 2: CPU Services Nodes (Days 3-5)
**Target: 1,000 CPU nodes**
- **Priority**: Support services (monitoring, logging, orchestration)
- **Strategy**: Rolling upgrade with surge capacity
- **Duration**: 6-8 hours per batch of 200 nodes
- **Critical services**: Use pod disruption budgets and multiple replicas

```yaml
# CPU Services Upgrade
Batch Size: 200 nodes
Surge Settings: max-surge=100, max-unavailable=50
Schedule: Maintenance windows (2-6 AM)
```

### Phase 3: Inference Fleet - Staged Approach (Days 6-12)
**Target: 1,500 A100 nodes**
- **Priority**: HIGH - Maintain inference availability
- **Strategy**: Canary deployment by availability zones

#### Phase 3a: Canary Zone (Days 6-7)
- Upgrade 500 nodes (1 AZ) with traffic shifting
- Monitor inference latency and throughput
- Validate model serving performance

#### Phase 3b: Production Zones (Days 8-12)
- Upgrade remaining 1,000 nodes in batches of 250
- Maintain 75% capacity during upgrades
- Use load balancer traffic management

```yaml
# A100 Inference Upgrade
Batch Size: 250 nodes
Surge Settings: max-surge=50, max-unavailable=0
Schedule: Coordinated with traffic patterns
Health Checks: Enhanced inference endpoint monitoring
```

### Phase 4: Training Fleet - Coordinated Approach (Days 13-20)
**Target: 2,000 H100 nodes**
- **Priority**: CRITICAL - Coordinate with training schedules
- **Strategy**: Checkpoint-aware rolling upgrade

#### Training Coordination Strategy:
1. **Schedule alignment**: Coordinate with ML teams for natural training breaks
2. **Checkpoint management**: Ensure all training jobs can save state
3. **Resource pools**: Maintain 60% training capacity during upgrades
4. **Priority queues**: Critical research gets priority on upgraded nodes

```yaml
# H100 Training Upgrade
Batch Size: 400 nodes (organized by training pools)
Surge Settings: max-surge=200, max-unavailable=200
Schedule: Aligned with training checkpoints
Pre-upgrade: Force checkpoint saves
Post-upgrade: Gradual workload migration
```

## Detailed Upgrade Procedures

### Pre-Node Upgrade Checklist
```bash
# 1. Drain nodes gracefully
kubectl drain $NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# 2. Verify workload migration
kubectl get pods --field-selector=spec.nodeName=$NODE_NAME

# 3. Check training job checkpoints
kubectl get jobs -l type=training --all-namespaces

# 4. Validate inference endpoint health
curl -f http://inference-lb/health
```

### Node Pool Upgrade Configuration
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
spec:
  upgradeSettings:
    maxSurge: 50
    maxUnavailable: 0
    strategy: BLUE_GREEN
  management:
    autoUpgrade: false
    autoRepair: true
  autoscaling:
    enabled: true
    minNodeCount: 0
    maxNodeCount: 500
```

## Monitoring & Validation

### Critical Metrics to Monitor
```yaml
Training Metrics:
- GPU utilization rates
- Training job completion times
- Checkpoint save/restore success rates
- Queue wait times

Inference Metrics:
- Request latency (p95, p99)
- Throughput (requests/second)
- Model loading times
- Error rates

Infrastructure Metrics:
- Node ready status
- Pod scheduling success
- Resource allocation efficiency
- Network connectivity
```

### Validation Scripts
```bash
#!/bin/bash
# Post-upgrade validation script

# Check GPU availability
kubectl get nodes -l accelerator=nvidia-tesla-h100 --no-headers | wc -l

# Validate GPU scheduling
kubectl run gpu-test --image=nvidia/cuda:11.8-base --limits=nvidia.com/gpu=1 --rm -it -- nvidia-smi

# Test inference endpoints
for endpoint in $(kubectl get svc -l type=inference -o jsonpath='{.items[*].status.loadBalancer.ingress[0].ip}'); do
  curl -f "http://$endpoint/health" || echo "Endpoint $endpoint failed"
done

# Check training job recovery
kubectl get jobs -l type=training --field-selector=status.conditions[*].type=Complete
```

## Risk Mitigation & Rollback

### Rollback Triggers
- **Training jobs fail to resume**: >10% checkpoint restore failures
- **Inference degradation**: >20% increase in P95 latency
- **GPU recognition issues**: GPUs not detected on >5% of nodes
- **Critical service failures**: Core ML platform services down >15 minutes

### Rollback Procedure
```bash
# 1. Stop ongoing upgrades
gcloud container node-pools update $POOL_NAME --no-enable-autoupgrade

# 2. Cordon upgraded nodes
kubectl get nodes -l node-version=1.30 | xargs kubectl cordon

# 3. Create rollback node pool
gcloud container node-pools create rollback-pool --node-version=1.29

# 4. Migrate workloads back
kubectl drain nodes-v1.30 --ignore-daemonsets --force
```

## Communication Plan

### Stakeholder Updates
- **Daily**: Operations team standup with upgrade status
- **Bi-daily**: ML teams notification of upcoming maintenance windows
- **Weekly**: Executive summary of progress and any issues
- **Immediate**: Critical issue escalation to all stakeholders

### Maintenance Windows
```
Development: Weekends, any time
CPU Services: Weekdays 2-6 AM
Inference: Coordinated with traffic patterns (typically 3-7 AM)
Training: Coordinated with research teams, typically during checkpoint intervals
```

## Timeline Summary
- **Week -2 to -1**: Preparation and testing
- **Week 1**: Development and CPU services (Days 1-5)
- **Week 2**: Inference fleet upgrade (Days 6-12)
- **Week 3**: Training fleet upgrade (Days 13-20)
- **Week 4**: Final validation and documentation

## Success Criteria
- ✅ Zero data loss from training jobs
- ✅ <5% increase in inference latency during upgrade
- ✅ 100% GPU recognition on upgraded nodes
- ✅ All critical services maintain >99.9% uptime
- ✅ Complete upgrade within 4-week window

This plan ensures your AI/ML workloads remain operational while systematically upgrading your entire 5,000-node fleet with minimal risk to your critical training and inference workloads.