# GKE Autopilot Upgrade Checklists

**Your setup:** 4 Autopilot clusters | Dev: 2 clusters on Rapid | Prod: 2 clusters on Stable | Upcoming: 1.31 → 1.32 auto-upgrade

Since you're on different channels (dev=Rapid, prod=Stable), your dev clusters likely already upgraded to 1.32. Use them to validate before your prod auto-upgrade hits.

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: [PROD_CLUSTER_1] [PROD_CLUSTER_2] | Mode: Autopilot | Channel: Stable
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] Dev clusters (Rapid channel) already at 1.32 - validation completed
- [ ] No deprecated API usage in prod workloads:
      - Check GKE deprecation insights dashboard in Console
      - Verify: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Third-party operators compatible with K8s 1.32:
      - [ ] Cert-manager version supports 1.32
      - [ ] Service mesh (Istio/ASM) version supports 1.32  
      - [ ] Policy controllers (Gatekeeper, etc.) version supports 1.32
      - [ ] Monitoring agents (Prometheus operator, etc.) version supports 1.32

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests (mandatory - pods rejected without them)
      - Verify: `kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.containers[*].resources.requests}{"\n"}{end}' | grep -v "map\|null"`
- [ ] No bare pods — all managed by Deployments/StatefulSets/Jobs
      - Check: `kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'`
- [ ] PDBs configured for critical workloads (not overly restrictive)
      - Verify: `kubectl get pdb -A -o wide` - ensure ALLOWED DISRUPTIONS > 0
- [ ] terminationGracePeriodSeconds ≤ 10 minutes (600s) for regular pods, ≤ 25s for Spot
- [ ] StatefulSet data backed up, PV reclaim policies verified as "Retain"

Dev Cluster Validation (Use Rapid clusters to validate 1.32)
- [ ] All workloads healthy on dev clusters at 1.32
- [ ] Application smoke tests passing on dev 1.32 clusters
- [ ] No admission webhook failures on dev clusters
- [ ] HPA/VPA behavior normal on dev clusters at 1.32
- [ ] Service mesh control plane healthy on dev clusters (if applicable)

Control Plane Timing (Your only upgrade control lever in Autopilot)
- [ ] Maintenance window configured for off-peak hours:
      ```
      gcloud container clusters update PROD_CLUSTER_1 \
        --region REGION \
        --maintenance-window-start "YYYY-MM-DDTHH:MM:SSZ" \
        --maintenance-window-duration 4h \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
      ```
- [ ] Maintenance exclusion applied if deferral needed (30-day max for "no upgrades"):
      ```
      gcloud container clusters update PROD_CLUSTER_1 \
        --region REGION \
        --add-maintenance-exclusion-name="defer-1.32" \
        --add-maintenance-exclusion-start=START_TIME \
        --add-maintenance-exclusion-end=END_TIME \
        --add-maintenance-exclusion-scope=no_upgrades
      ```

Ops Readiness
- [ ] Auto-upgrade notification timeline confirmed (1.32 arrives in Stable next month)
- [ ] Baseline metrics captured (error rates, latency, throughput) from current 1.31 clusters
- [ ] Monitoring active - Cloud Monitoring dashboards for cluster health
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware - Autopilot upgrades are fully automated
- [ ] Rollback plan: minimal options in Autopilot (GKE support required for CP downgrade)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.32

Cluster Health (Regional CP remains available during upgrade)
- [ ] Control plane at 1.32: 
      `gcloud container clusters describe PROD_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes at 1.32 (GKE-managed, automatic):
      `kubectl get nodes -o wide`
- [ ] All nodes Ready: `kubectl get nodes | grep -v Ready`
- [ ] System pods healthy: `kubectl get pods -n kube-system | grep -v Running`
- [ ] No PDB violations logged during upgrade

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No failed pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completed successfully: `kubectl get jobs -A`
- [ ] Ingress/load balancers responding (test external endpoints)
- [ ] Application smoke tests passing

API & Compatibility
- [ ] No admission webhook failures in events:
      `kubectl get events -A --field-selector type=Warning | grep -i webhook`
- [ ] HPA scaling behavior normal: `kubectl describe hpa -A`
- [ ] VPA recommendations stable: `kubectl describe vpa -A`
- [ ] No new deprecation warnings: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`

Observability & Performance
- [ ] Metrics collection active (no gaps during upgrade window)
- [ ] Log aggregation flowing normally
- [ ] Error rates within pre-upgrade baseline
- [ ] API latency (p95/p99) within normal range
- [ ] No unexpected 503 errors from API server

Cross-Cluster Validation
- [ ] Both prod clusters (PROD_CLUSTER_1, PROD_CLUSTER_2) successfully upgraded
- [ ] Load balancing between clusters normal (if using multi-cluster setup)
- [ ] All 4 clusters now at consistent 1.32 version

Documentation
- [ ] Upgrade completion logged in runbook/changelog  
- [ ] Any issues encountered documented for next upgrade
- [ ] Lessons learned shared with team
```

## Key Autopilot Considerations

**What GKE handles automatically:**
- Node pool upgrade strategy (always surge, ~20 nodes concurrently)
- Node pool creation, cordoning, draining, deletion
- System component upgrades
- Regional control plane stays available throughout

**Your control points:**
- **Timing:** Maintenance windows (when auto-upgrade happens)
- **Deferral:** Maintenance exclusions (up to 30 days delay)
- **Workload preparation:** Resource requests, PDBs, graceful shutdown

**Validation advantage:** Since your dev clusters on Rapid channel likely upgraded to 1.32 weeks ago, use them as your validation environment. Any issues with 1.32 should surface there first.

**Channel strategy note:** Your current setup (dev=Rapid, prod=Stable) gives natural sequencing but prevents rollout sequencing. Consider moving both environments to the same channel (Regular) with rollout sequencing for more automated coordination in the future.