# GKE Upgrade Plan: Large-Scale LLM Training Cluster

## Executive Summary

**Critical constraints identified:**
- **512 H100 nodes (4,096 GPUs total)** - massive scale requiring careful coordination
- **2-3 week training runs** - cannot tolerate mid-job eviction
- **GPUDirect-TCPXO** - high-performance interconnect with strict version requirements
- **A3 Mega nodes** - likely fixed GPU reservation with no surge capacity

**Recommended approach:** Maintenance exclusion during active training + scheduled upgrade between training campaigns using custom upgrade strategy.

---

## Version & Interconnect Compatibility Check

### GPUDirect-TCPXO Requirements
```bash
# Verify current GPUDirect-TCPX version support
gcloud container get-server-config --zone ZONE --format="yaml(validMasterVersions)" | grep 1.32

# Check release notes for A3 Mega + GPUDirect-TCPXO compatibility with 1.32
# Critical: GPUDirect-TCPXO requires specific GKE versions for A3 Mega machines
```

**Pre-upgrade validation required:** GPUDirect-TCPXO on A3 Mega has strict version dependencies. Before any upgrade:
1. Verify GKE 1.32 supports GPUDirect-TCPXO on A3 Mega in release notes
2. Test interconnect topology survives upgrade in a staging cluster with representative RDMA workloads
3. Confirm placement policy keeps replacement nodes in the same compact placement group

---

## Immediate Action: Protect Active Training Run

Since you have an active 2-3 week training run, **immediately apply a maintenance exclusion** to prevent auto-upgrades:

```bash
# Block ALL upgrades during training campaign (30-day max)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d "+30 days" -Iseconds) \
  --add-maintenance-exclusion-scope no_upgrades
```

**Alternative for longer campaigns:** Use "no minor or node upgrades" exclusion (no time limit, tracks EoS):
```bash
# Allows control plane patches, blocks disruptive upgrades until EoS
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

---

## Upgrade Strategy: Custom Workflow Between Training Runs

For a 512-node GPU cluster with long-running training, **standard surge/blue-green won't work**:
- **Surge**: No GPU surge capacity available with fixed reservations
- **Standard blue-green**: Would require 1,024 H100 nodes (2x cost, likely impossible)
- **Autoscaled blue-green**: Still needs significant extra capacity for 512 nodes

### Recommended: AI Host Maintenance Strategy

Use GKE's AI host maintenance approach designed for large training clusters:

**Phase 1: Control Plane Upgrade (Low Risk)**
```bash
# Remove exclusion temporarily for CP upgrade only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-protection"

# Upgrade control plane during training gap
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Re-apply node protection
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Phase 2: Coordinated Node Upgrade**

**Option A: Parallel Strategy (Recommended for Training)**
- Scale training workload to zero (or checkpoint and pause)
- Apply AI host maintenance to ALL nodes simultaneously
- Wait ~4 hours for host maintenance completion
- Restart training workload

```bash
# During planned training gap:
# 1. Checkpoint and stop training job
kubectl scale deployment training-workload --replicas=0

# 2. Apply maintenance label to all GPU nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-accelerator=nvidia-h100-80gb \
  cloud.google.com/perform-maintenance=true

# 3. Monitor maintenance completion (~4 hours)
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-h100-80gb -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,MAINTENANCE:.metadata.labels.cloud\.google\.com/perform-maintenance'

# 4. Once all nodes complete maintenance, restart training
kubectl scale deployment training-workload --replicas=DESIRED_REPLICAS
```

**Option B: Rolling Strategy (If Some Capacity Can Continue Serving)**
- Only if you have inference workloads that must keep serving
- Upgrade nodes in smaller batches by zone/failure domain
- Maintains partial capacity throughout

---

## Pre-Upgrade Validation Checklist

```
Large-Scale GPU Training Cluster Upgrade Checklist

Version Compatibility
- [ ] GKE 1.32.X supports GPUDirect-TCPXO on A3 Mega (check release notes)
- [ ] GPU driver compatibility confirmed with target version
- [ ] Staging cluster tested with representative RDMA workloads
- [ ] Compact placement policy verified to survive upgrade

Training Job Protection
- [ ] Active training run checkpointed and can resume post-upgrade
- [ ] Training data and checkpoints backed up to persistent storage
- [ ] Job orchestrator (Kubernetes Job, custom controller) tested for restart capability
- [ ] Expected training resume time calculated and communicated

Infrastructure Readiness
- [ ] Maintenance exclusion active to prevent auto-upgrades
- [ ] Upgrade scheduled during planned training gap (between campaigns)
- [ ] GPU reservation confirmed - no expectation of surge capacity
- [ ] Network topology (VPC, subnets, firewall) supports GPUDirect-TCPXO post-upgrade
- [ ] Monitoring and alerting active for 512-node upgrade operation

Ops Readiness
- [ ] Extended maintenance window planned (4+ hours for parallel host maintenance)
- [ ] Training team aware of upgrade schedule and expected downtime
- [ ] On-call team available during upgrade window
- [ ] Rollback plan documented (may require support involvement for 512-node cluster)
```

---

## Timeline Recommendation

**Immediate (Today):**
- Apply maintenance exclusion to protect active training run
- Begin staging cluster testing with GKE 1.32 + GPUDirect-TCPXO

**Next Training Gap (2-3 weeks):**
- Upgrade control plane during brief gap between training jobs
- Re-apply node protection exclusion

**Next Extended Gap (When Training Campaign Ends):**
- Execute parallel AI host maintenance strategy
- All 512 nodes upgraded simultaneously in ~4 hours
- Resume training operations

---

## Risk Mitigation

**Interconnect Risk:** GPUDirect-TCPXO topology may break if nodes land in different placement groups. Mitigation:
- Test in staging cluster first (mandatory)
- Verify compact placement policy survives upgrade
- Monitor RDMA connectivity post-upgrade before resuming training

**Scale Risk:** 512-node operations may exceed GKE's normal upgrade parallelism limits (~20 nodes). Mitigation:
- Use AI host maintenance (designed for large GPU clusters)
- Contact GKE support for 512-node upgrade coordination if needed

**Training Resume Risk:** Multi-week training jobs have complex checkpointing requirements. Mitigation:
- Validate checkpoint/resume process in staging
- Ensure training orchestrator handles node restart correctly
- Plan for potential training restart from last checkpoint

---

## Key Commands Reference

```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name,currentMasterVersion,nodePools[].version,nodePools[].instanceGroupUrls)"

# Monitor GPU node versions during upgrade
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-h100-80gb \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[?(@.type==\"Ready\")].status

# Verify GPUDirect-TCPXO post-upgrade (run from training pod)
# Check RDMA devices and topology
lspci | grep Mellanox
ibstat
nvidia-smi topo -m
```

**Next Steps:** Apply the immediate maintenance exclusion, then begin staging cluster validation before planning the full upgrade during your next training gap.