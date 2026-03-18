# GKE Autopilot 1.29 → 1.30 Upgrade Checklists

**Environment:** 4 Autopilot clusters (2 dev on Rapid, 2 prod on Stable)
**Current version:** 1.29 | **Target version:** 1.30
**Upgrade timing:** Auto-upgrade scheduled for next month (prod clusters only)

---

## Pre-Upgrade Checklist

```
CLUSTER IDENTIFICATION
- [ ] Dev Cluster 1 (Rapid) — Name: _________________
- [ ] Dev Cluster 2 (Rapid) — Name: _________________
- [ ] Prod Cluster 1 (Stable) — Name: _________________
- [ ] Prod Cluster 2 (Stable) — Name: _________________

VERSION COMPATIBILITY (all clusters)
- [ ] Version 1.30 confirmed available in Rapid release channel (dev clusters)
- [ ] Version 1.30 confirmed available in Stable release channel (prod clusters)
  Command: gcloud container get-server-config --zone ZONE --format="yaml(channels)"
- [ ] GKE 1.29 → 1.30 release notes reviewed for breaking changes
  Link: https://cloud.google.com/kubernetes-engine/docs/release-notes
- [ ] No deprecated API usage across all clusters
  Command: Check GKE deprecation insights dashboard in Cloud Console
- [ ] All third-party operators/controllers verified compatible with 1.30
  (e.g., Istio, Prometheus, cert-manager, nginx-ingress — list your own)
  - Operator/controller: __________________ | Version: _________ | Status: ✓
  - Operator/controller: __________________ | Version: _________ | Status: ✓
  - Operator/controller: __________________ | Version: _________ | Status: ✓
- [ ] Admission webhooks tested/reviewed for 1.30 compatibility

WORKLOAD READINESS (all clusters — Autopilot-specific)
- [ ] All containers have resource requests AND limits defined
  Command: kubectl get pods -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,REQUESTS:.spec.containers[*].resources.requests,LIMITS:.spec.containers[*].resources.limits | grep -i '<none>'
  Note: Autopilot requires requests on all containers; pods without requests will fail to schedule
- [ ] Pod Disruption Budgets (PDBs) configured for critical workloads (not overly restrictive)
  Command: kubectl get pdb -A
- [ ] No bare pods — all workloads managed by Deployment, StatefulSet, DaemonSet, or Job
  Command: kubectl get pods -A --field-selector=metadata.ownerReferences[0].kind=""
- [ ] terminationGracePeriodSeconds set appropriately for graceful shutdown (check StatefulSets, long-running batch jobs)
  Command: kubectl get statefulsets -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,GRACE:.spec.terminationGracePeriodSeconds
- [ ] StatefulSet persistent volume backups completed and verified
- [ ] StatefulSet PV reclaim policies checked (Retain if data migration needed, Delete if ephemeral)
- [ ] GPU workload compatibility verified with 1.30 node image (if applicable)
  Command: gcloud container get-server-config --zone ZONE --format="json" | jq '.validMasterVersions[] | select(.version == "1.30.0")'

SECURITY & MONITORING
- [ ] Cloud Monitoring dashboards verified and active
- [ ] Baseline metrics captured: error rates, latency (p50/p95/p99), pod restart count
- [ ] Log aggregation pipeline active (Cloud Logging, Stackdriver, or third-party)
- [ ] PagerDuty/alerting configured for upgrade-window incidents (if applicable)

MAINTENANCE WINDOWS (Autopilot controls auto-upgrade timing)
- [ ] Auto-upgrade window reviewed for prod clusters (Stable channel)
  Command: gcloud container clusters describe CLUSTER --zone ZONE --format="value(maintenancePolicy)"
- [ ] If needed, update maintenance window to off-peak hours
  Command: gcloud container clusters update CLUSTER --zone ZONE --maintenance-window-start=YYYY-MM-DD --maintenance-window-end=YYYY-MM-DD --maintenance-window-recurrence="..."
- [ ] Maintenance exclusion set for any freeze periods (up to 30 days)
  Command: gcloud container clusters update CLUSTER --zone ZONE --add-maintenance-exclusion-start=YYYY-MM-DD --add-maintenance-exclusion-end=YYYY-MM-DD

OPS READINESS
- [ ] Upgrade window communicated to stakeholders, on-call team, and SREs
- [ ] Rollback plan documented (if auto-upgrade fails, manual downgrade procedure exists)
- [ ] On-call team briefed and available during upgrade window
- [ ] Change log entry prepared for post-upgrade documentation
```

---

## Post-Upgrade Checklist

Run these checks after all 4 clusters have upgraded to 1.30.

```
CLUSTER HEALTH (run after each cluster upgrade completes)

Dev Cluster 1 (Rapid)
- [ ] Control plane at 1.30: gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"
- [ ] All nodes at 1.30: gcloud container node-pools list --cluster CLUSTER --zone ZONE
- [ ] All nodes Ready: kubectl get nodes
- [ ] kube-system pods healthy: kubectl get pods -n kube-system
- [ ] No eviction events: kubectl get events -n kube-system --sort-by='.lastTimestamp' | grep Evict

Dev Cluster 2 (Rapid)
- [ ] Control plane at 1.30: gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"
- [ ] All nodes at 1.30: gcloud container node-pools list --cluster CLUSTER --zone ZONE
- [ ] All nodes Ready: kubectl get nodes
- [ ] kube-system pods healthy: kubectl get pods -n kube-system
- [ ] No eviction events: kubectl get events -n kube-system --sort-by='.lastTimestamp' | grep Evict

Prod Cluster 1 (Stable)
- [ ] Control plane at 1.30: gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"
- [ ] All nodes at 1.30: gcloud container node-pools list --cluster CLUSTER --zone ZONE
- [ ] All nodes Ready: kubectl get nodes
- [ ] kube-system pods healthy: kubectl get pods -n kube-system
- [ ] No eviction events: kubectl get events -n kube-system --sort-by='.lastTimestamp' | grep Evict

Prod Cluster 2 (Stable)
- [ ] Control plane at 1.30: gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"
- [ ] All nodes at 1.30: gcloud container node-pools list --cluster CLUSTER --zone ZONE
- [ ] All nodes Ready: kubectl get nodes
- [ ] kube-system pods healthy: kubectl get pods -n kube-system
- [ ] No eviction events: kubectl get events -n kube-system --sort-by='.lastTimestamp' | grep Evict

WORKLOAD HEALTH (all clusters)
- [ ] All Deployments at desired replica count: kubectl get deployments -A
- [ ] No CrashLoopBackOff pods: kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
- [ ] No Pending pods (except expected): kubectl get pods -A --field-selector=status.phase=Pending
- [ ] All StatefulSets fully ready and have stable DNS: kubectl get statefulsets -A
- [ ] No stuck PDBs blocking pod scheduling: kubectl get pdb -A
- [ ] Ingress/load balancers responding and backend health good

APPLICATION VALIDATION
- [ ] Smoke tests passing (health checks, critical flows)
- [ ] Manual spot-checks on key applications
- [ ] Database connectivity verified (if using managed databases, check connection pooling)
- [ ] File upload/download paths working (if applicable)
- [ ] Third-party services (payment, auth, CDN) responsive

OBSERVABILITY (all clusters)
- [ ] Metrics pipeline active, no collection gaps: confirm last metric datapoint within 1 min
- [ ] Logs flowing to aggregation: check log volume in last 5 minutes
- [ ] Error rates within pre-upgrade baseline (±10% acceptable)
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline (±10% acceptable)
- [ ] No new error patterns in logs or error tracking (Sentry, DataDog, etc.)
- [ ] CPU, memory, disk usage on nodes stable

VERSION SKEW VERIFICATION
- [ ] Nodes within 2 minor versions of control plane (should all be 1.30 now)
  Command: kubectl get nodes -o wide | grep -E 'v1\.[0-9]+\.[0-9]+'

CLEANUP
- [ ] Upgrade documented in team changelog/wiki
- [ ] Lessons learned captured (what went well, issues encountered, fixes applied)
- [ ] On-call team debriefing completed
- [ ] Metrics and incident reports (if any) archived for future reference
```

---

## Key Differences for Autopilot Clusters

Unlike Standard clusters, Autopilot handles these automatically:
- **Node pool management** — Google manages node pool upgrades and surge settings
- **OS patching** — automatic and transparent
- **Control plane upgrades** — scheduled during maintenance windows you set

**What you still control:**
- **Release channel enrollment** (Rapid/Regular/Stable) — set at cluster creation
- **Maintenance windows** — when Google can auto-upgrade (gcloud command above)
- **Workload readiness** — ensure all pods have resource requests and PDBs where needed
- **Monitoring & validation** — confirm health after upgrade completes

---

## Rollback Procedure (if needed)

If prod clusters encounter issues post-upgrade, you can downgrade from 1.30 back to 1.29 for up to 30 days:

```bash
gcloud container clusters update CLUSTER \
  --master-version 1.29.99 \
  --zone ZONE

# Monitor control plane version:
gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"

# Nodes will follow within 24 hours
```

**Note:** Autopilot doesn't support arbitrary downgrade timing — downgrades respect the next auto-upgrade window.

---

## Quick Reference: Upgrade Commands

```bash
# View current versions across all clusters:
gcloud container clusters describe prod-cluster-1 --zone us-central1-a --format="value(currentMasterVersion, masterVersion)"

# View maintenance window:
gcloud container clusters describe prod-cluster-1 --zone us-central1-a --format="value(maintenancePolicy)"

# Manually trigger upgrade (if not auto-upgrades):
gcloud container clusters upgrade prod-cluster-1 \
  --master-version 1.30.99 \
  --zone us-central1-a

# Monitor upgrade progress:
gcloud container operations list --zone us-central1-a --filter="cluster:prod-cluster-1"

# Check node readiness during/after upgrade:
kubectl get nodes -w
kubectl get pods -n kube-system -w
```

---

## Timeline Notes

- **Dev clusters (Rapid channel):** Version 1.30 typically available within weeks of release
- **Prod clusters (Stable channel):** Version 1.30 available after Regular channel validation (usually 2-3 months after Rapid)
- **Auto-upgrade window:** Prod will upgrade automatically during the next maintenance window after 1.30 is available in Stable
- **Pre-freeze checklist:** Complete 2-3 weeks before the expected auto-upgrade window

Good luck with your upgrade!
