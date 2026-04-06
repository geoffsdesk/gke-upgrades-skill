# GKE Autopilot Upgrade Checklists
**Clusters:** 4 Autopilot clusters (2 dev/Rapid, 2 prod/Stable)  
**Upgrade:** 1.31 → 1.32 (auto-upgrade next month)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: 2 dev (Rapid) | 2 prod (Stable) | Mode: Autopilot

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes (https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] No deprecated API usage detected:
      - [ ] Check GKE deprecation insights in console (Insights tab → "Deprecations and Issues")
      - [ ] Run: kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
- [ ] Kubernetes 1.32 deprecations reviewed (especially for workloads using beta APIs)
- [ ] Third-party operators/controllers compatibility verified for K8s 1.32:
      - [ ] Service mesh (Istio/ASM) version supports 1.32
      - [ ] cert-manager version supports 1.32
      - [ ] Other admission controllers/operators checked

Workload Readiness (Autopilot Requirements)
- [ ] ALL containers have resource requests set (mandatory in Autopilot):
      ```
      kubectl get pods -A -o json | jq -r '.items[] | select(.spec.containers[]?.resources.requests == null) | "\(.metadata.namespace)/\(.metadata.name)"'
      ```
- [ ] PDBs configured for critical workloads (not overly restrictive):
      ```
      kubectl get pdb -A -o wide
      ```
- [ ] No bare pods — all managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds ≤ 10 minutes (600s) for regular pods, ≤ 25s for Spot pods (Autopilot limits)
- [ ] StatefulSet data backed up if applicable (PV snapshots, app-level backups)

Channel & Upgrade Timing Validation
- [ ] Dev clusters (Rapid) already upgraded or will upgrade first
- [ ] Prod clusters (Stable) will upgrade after dev validation completes
- [ ] Maintenance windows configured for prod clusters if specific timing needed:
      ```
      gcloud container clusters describe PROD_CLUSTER_1 --region REGION --format="value(maintenancePolicy)"
      ```
- [ ] No maintenance exclusions blocking the upgrade (check console or gcloud)
- [ ] Confirm 1.32 is available in Stable channel:
      ```
      gcloud container get-server-config --region REGION --format="yaml(channels)"
      ```

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring dashboards, alerting)
- [ ] Baseline metrics captured (error rates, latency, pod restart rates)
- [ ] Team notified of upgrade timeline (dev first, then prod)
- [ ] On-call schedule covers upgrade period
- [ ] Rollback plan documented (control plane patch downgrades possible, but not minor)

Dev Environment Validation (Complete Before Prod Upgrade)
- [ ] Dev clusters upgraded successfully
- [ ] Smoke tests passed on dev
- [ ] No regression in application functionality
- [ ] Performance within acceptable range
- [ ] Any issues identified and mitigated
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot

Run for each cluster after upgrade completes:

Cluster Health
- [ ] Control plane at 1.32.x: 
      ```
      gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"
      ```
- [ ] All nodes at 1.32.x (Autopilot manages this automatically):
      ```
      kubectl get nodes -o wide
      ```
- [ ] All nodes Ready status:
      ```
      kubectl get nodes | grep -v Ready || echo "All nodes Ready"
      ```
- [ ] System pods healthy:
      ```
      kubectl get pods -n kube-system
      kubectl get pods -n gke-system
      kubectl get pods -n gke-managed-filestorecsi
      ```

Workload Health
- [ ] All deployments at desired replica count:
      ```
      kubectl get deployments -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,DESIRED:.spec.replicas,CURRENT:.status.replicas,UP-TO-DATE:.status.updatedReplicas,AVAILABLE:.status.availableReplicas
      ```
- [ ] No CrashLoopBackOff or long-Pending pods:
      ```
      kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
      ```
- [ ] StatefulSets fully ready:
      ```
      kubectl get statefulsets -A
      ```
- [ ] Jobs completed successfully (check recent jobs):
      ```
      kubectl get jobs -A --sort-by=.metadata.creationTimestamp
      ```

Application & API Validation
- [ ] Ingress/LoadBalancer services responding:
      ```
      kubectl get ingress -A
      kubectl get services -A --field-selector spec.type=LoadBalancer
      ```
- [ ] Application health checks passing
- [ ] API endpoints returning expected responses
- [ ] Authentication/authorization working (RBAC, service accounts)
- [ ] No admission webhook failures:
      ```
      kubectl get events -A --field-selector type=Warning | grep -i webhook
      ```

Performance & Observability
- [ ] Metrics collection active (no gaps in Cloud Monitoring)
- [ ] Application logs flowing normally
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within acceptable range
- [ ] Resource utilization normal:
      ```
      kubectl top nodes
      kubectl top pods -A --sort-by=cpu
      ```

Post-Upgrade Actions
- [ ] Document upgrade completion with any issues encountered
- [ ] Update internal documentation with new cluster versions
- [ ] Remove any temporary workarounds applied for the upgrade
- [ ] Schedule next upgrade planning session (quarterly review recommended)
```

## Key Notes for Your Setup

**Upgrade Sequence:** Your dev clusters on Rapid channel should upgrade to 1.32 first (likely already happened or happening soon). Wait for dev validation before prod upgrades occur on Stable channel.

**Autopilot Advantages:** 
- No node pool management needed - Google handles all node upgrades automatically
- Control plane stays highly available during upgrades (all Autopilot clusters are regional)
- Simpler rollback options for control plane patches

**Critical Items:**
1. **Resource requests are mandatory** - any missing requests will cause pod failures
2. **PDB timeout is 1 hour max** - overly restrictive PDBs will eventually be bypassed
3. **Grace period limits** - 10 min for regular pods, 25 sec for Spot pods

Since you're getting notifications about next month's upgrade, you have good lead time to validate dev clusters first and address any compatibility issues before prod.