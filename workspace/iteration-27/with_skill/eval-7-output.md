# GKE Multi-Environment Rollout Strategy

**Cluster Fleet:** 12 Standard clusters across 3 environments  
**Current:** 1.32 → **Target:** 1.33  
**Channel:** Regular (all environments)  
**Strategy:** Progressive rollout with validation gates

## Rollout Sequencing

Since all environments are on Regular channel, you have two strategic options:

### Option A: Automated Fleet Rollout (Recommended)
Use GKE's rollout sequencing feature to automatically orchestrate upgrades across environments:

```bash
# Configure rollout sequence: dev → staging → prod
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-project \
    --default-upgrade-soaking=48h

# Staging fleet waits for dev completion + 48h soak
gcloud container fleet clusterupgrade update \
    --project=staging-project \
    --upstream-fleet=dev-project \
    --default-upgrade-soaking=24h

# Prod fleet waits for staging completion + 24h soak
gcloud container fleet clusterupgrade update \
    --project=prod-project \
    --upstream-fleet=staging-project \
    --default-upgrade-soaking=72h
```

**How it works:** When 1.33 becomes the auto-upgrade target in Regular channel, dev clusters upgrade first. After completion + 48h soak, staging upgrades. After staging completion + 24h soak, prod upgrades.

### Option B: Manual Control with Maintenance Exclusions
Block auto-upgrades and manually trigger upgrades in sequence:

```bash
# Apply "no minor" exclusion to all clusters to prevent auto-upgrades
for cluster in staging-cluster-{1..4} prod-cluster-{1..4}; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --add-maintenance-exclusion-scope no_minor_upgrades \
        --add-maintenance-exclusion-until-end-of-support
done
```

Then manually trigger upgrades following the timeline below.

## Recommended Timeline (Option B - Manual Control)

### Week 1: Dev Environment (4 clusters)
**Day 1-2:** Upgrade dev clusters in pairs
```bash
# Upgrade dev clusters 1-2 first
gcloud container clusters upgrade dev-cluster-1 --zone ZONE --cluster-version 1.33
gcloud container clusters upgrade dev-cluster-2 --zone ZONE --cluster-version 1.33

# Wait 24h, monitor, then upgrade dev clusters 3-4
gcloud container clusters upgrade dev-cluster-3 --zone ZONE --cluster-version 1.33
gcloud container clusters upgrade dev-cluster-4 --zone ZONE --cluster-version 1.33
```

**Day 3-7:** Validation period
- Run integration tests
- Monitor application health
- Validate new 1.33 features
- Check for any regression issues

### Week 2: Staging Environment (4 clusters)
**Prerequisites:** Dev validation successful, no blocking issues

**Day 8-9:** Upgrade staging clusters
```bash
# Remove maintenance exclusion from staging clusters
for cluster in staging-cluster-{1..4}; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --remove-maintenance-exclusion-name "no-minor-upgrades"
done

# Upgrade staging clusters in pairs
# Control plane first, then node pools
```

**Day 10-14:** Extended validation
- Performance testing
- Load testing
- Security scanning
- Stakeholder sign-off

### Week 3: Production Environment (4 clusters)
**Prerequisites:** Staging validation successful

**Day 15-17:** Upgrade production clusters (most conservative)
```bash
# Upgrade prod clusters one at a time with extended soak
gcloud container clusters upgrade prod-cluster-1 --zone ZONE --cluster-version 1.33
# Wait 24h minimum between each prod cluster
```

## Per-Cluster Upgrade Sequence

For each cluster, follow this control plane → node pool sequence:

### 1. Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.33
```

### 2. Node Pool Strategy (Standard Clusters)
Since you have Standard clusters, configure surge settings per workload type:

**Stateless workloads:**
```bash
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 2 \
    --max-unavailable-upgrade 0
```

**Stateful workloads (databases, etc.):**
```bash
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

**GPU pools (if any):**
```bash
gcloud container node-pools update POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

### 3. Upgrade Node Pools
```bash
gcloud container node-pools upgrade POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.33
```

## Validation Gates

**After each environment:**

```bash
# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Workload health
kubectl get deployments -A
kubectl get statefulsets -A

# Version confirmation
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].version)"
```

## Risk Mitigation

### Maintenance Windows
Configure off-peak windows for each environment:

```bash
# Example: Saturday 2-6 AM maintenance window
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Emergency Rollback Plan
**Control plane:** Contact GKE support for emergency downgrade  
**Node pools:** Create new pools at 1.32, migrate workloads, delete upgraded pools

### Monitoring
- Enable cluster notifications for upgrade events
- Monitor GKE deprecation insights dashboard
- Set up Cloud Logging alerts for upgrade failures

## Pre-Flight Checklist
- [ ] All clusters verified on Regular channel
- [ ] 1.33 available in Regular channel
- [ ] Deprecated API usage checked (run on dev first)
- [ ] PDBs configured for critical workloads
- [ ] Maintenance exclusions applied to staging/prod
- [ ] Rollback procedures documented
- [ ] On-call team briefed

**Estimated Total Duration:** 3 weeks with proper validation  
**Risk Level:** Low (progressive rollout with validation gates)

Would you like me to adjust the timeline or add specific validation steps for your workload types?