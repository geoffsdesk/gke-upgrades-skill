# GKE Autopilot Upgrade Checklists: 1.31 → 1.32

**Environment:** 4 Autopilot clusters | Dev: Rapid channel | Prod: Stable channel | Target: 1.32

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist
- [ ] Clusters: 2 dev (Rapid), 2 prod (Stable) | Mode: Autopilot | Channels: Rapid/Stable
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & Breaking Changes
- [ ] 1.32 release notes reviewed for breaking changes (https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] No deprecated API usage detected:
      - [ ] Check GKE deprecation insights in console (Insights tab → "Deprecations and Issues")
      - [ ] Run: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated` on all clusters
- [ ] Third-party operators/controllers compatible with Kubernetes 1.32:
      - [ ] Service mesh (Istio/ASM) versions checked
      - [ ] Monitoring stack (Prometheus operator, etc.)
      - [ ] CI/CD tools (Argo CD, Flux, etc.)
      - [ ] Any custom operators or CRDs

Workload Readiness (Autopilot Requirements)
- [ ] All containers have resource requests set (mandatory in Autopilot):
      ```bash
      kubectl get pods -A -o json | jq -r '.items[] | select(.spec.containers[]?.resources.requests == null) | "\(.metadata.namespace)/\(.metadata.name)"'
      ```
- [ ] PDBs configured for critical workloads (not overly restrictive):
      ```bash
      kubectl get pdb -A -o wide
      ```
- [ ] No bare pods — all managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds ≤ 600s (10 min limit in Autopilot, 25s for Spot)
- [ ] StatefulSet data backed up if applicable

Validation Path (Channel Strategy)
- [ ] Dev clusters on Rapid will upgrade first — use as validation
- [ ] Prod clusters on Stable will upgrade ~2 weeks after dev
- [ ] Smoke tests prepared for dev validation before prod upgrade
- [ ] Communication plan: dev upgrade results → prod go/no-go decision

Infrastructure & Timing
- [ ] Maintenance windows configured for prod clusters (off-peak hours):
      ```bash
      gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(maintenancePolicy)"
      ```
- [ ] Consider temporary "no upgrades" exclusion if more time needed:
      ```bash
      # 30-day max, blocks all upgrades including patches
      gcloud container clusters update CLUSTER_NAME --region REGION \
        --add-maintenance-exclusion-name "defer-132-upgrade" \
        --add-maintenance-exclusion-start-time "YYYY-MM-DDTHH:MM:SSZ" \
        --add-maintenance-exclusion-end-time "YYYY-MM-DDTHH:MM:SSZ" \
        --add-maintenance-exclusion-scope no_upgrades
      ```

Observability & Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput) from dev and prod
- [ ] Upgrade timeline communicated to stakeholders
- [ ] On-call team aware — dev upgrade first, then prod 1-2 weeks later
- [ ] Scheduled upgrade notifications enabled (72h advance notice):
      ```bash
      gcloud container clusters update CLUSTER_NAME --region REGION --enable-scheduled-upgrades
      ```
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist

Control Plane Health
- [ ] All clusters at 1.32: 
      ```bash
      gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"
      ```
- [ ] All nodes automatically upgraded by GKE (Autopilot manages this)
- [ ] System pods healthy in all clusters:
      ```bash
      kubectl get pods -n kube-system
      kubectl get pods -n gke-system
      ```

Workload Health Validation
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: 
      ```bash
      kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
      ```
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/Gateway APIs responding correctly
- [ ] Application smoke tests passing in dev clusters
- [ ] Application smoke tests passing in prod clusters (after dev validation)

Autopilot-Specific Checks
- [ ] Resource requests still properly set (Autopilot requirement maintained)
- [ ] Pod scheduling working normally (no resource allocation issues)
- [ ] Horizontal Pod Autoscaler functioning correctly
- [ ] Vertical Pod Autoscaler recommendations appropriate

API & Admission Webhook Health
- [ ] No admission webhook failures:
      ```bash
      kubectl get events -A --field-selector type=Warning | grep webhook
      ```
- [ ] API latency within normal range (check Cloud Monitoring)
- [ ] Custom Resource Definitions working correctly
- [ ] Service mesh (if applicable) proxy injection working

Observability & Metrics
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] No increase in 5xx errors or failed health checks

Cleanup & Documentation
- [ ] Remove temporary maintenance exclusions if applied
- [ ] Update documentation with new cluster versions
- [ ] Upgrade timeline and results documented
- [ ] Lessons learned captured for next upgrade cycle
```

## Key Autopilot Considerations

- **No node pool management needed** — GKE handles all node upgrades automatically using surge strategy
- **Dev-first validation** — Your Rapid dev clusters will upgrade first, giving you ~2 weeks to validate before Stable prod clusters upgrade
- **Resource requests mandatory** — Any pods without resource requests will fail to schedule post-upgrade
- **Limited troubleshooting** — No SSH access; use `kubectl debug` and Cloud Logging for diagnostics
- **Grace period limits** — 10 minutes max for regular pods, 25 seconds for Spot workloads

Your channel strategy (dev=Rapid, prod=Stable) provides natural progressive rollout. Use the dev cluster upgrades as your canary validation before prod receives the same version.