# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) + 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (auto-upgrade scheduled next month)  
**Mode:** Autopilot (Google manages nodes)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: [DEV-CLUSTER-1], [DEV-CLUSTER-2] (Rapid) | [PROD-CLUSTER-1], [PROD-CLUSTER-2] (Stable)

Compatibility & Breaking Changes
- [ ] 1.32 available in Stable channel: `gcloud container get-server-config --region REGION --format="yaml(channels.STABLE)"`
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] K8s 1.32 breaking changes reviewed: https://kubernetes.io/docs/reference/using-api/deprecation-guide/#v1-32
- [ ] GKE 1.32 release notes reviewed for Autopilot-specific changes
- [ ] Third-party operators/controllers tested against 1.32 in dev clusters

Workload Readiness (Critical for Autopilot)
- [ ] All containers have resource requests (mandatory - pods will be rejected without them)
- [ ] Resource requests realistic (not placeholder values like 100m/128Mi)
- [ ] PDBs configured for critical workloads (not overly restrictive - allow at least 1 disruption)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/etc
- [ ] terminationGracePeriodSeconds ≤ 600s (Autopilot enforces 10min max)
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database operators (if any) compatible with K8s 1.32

Autopilot-Specific Checks
- [ ] No unsupported configurations that will be rejected post-upgrade
- [ ] Workloads using supported machine types (Autopilot auto-provisions)
- [ ] Security contexts within Autopilot constraints (no privileged containers)
- [ ] NetworkPolicies validated (if using GKE Dataplane V2)

Upgrade Timing & Control
- [ ] Dev clusters already on 1.32 (should have upgraded weeks ago on Rapid)
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Consider maintenance exclusion if upgrade timing conflicts with critical business periods:
      - "No upgrades" (30-day max, emergency use)
      - "No minor or node upgrades" (up to EoS, blocks 1.32 upgrade)
- [ ] Stakeholders notified of upcoming auto-upgrade window

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring dashboards for GKE)
- [ ] Baseline metrics captured (error rates, latency, resource usage)
- [ ] On-call team aware of upgrade schedule
- [ ] Incident response plan ready
- [ ] Dev cluster upgrade lessons learned documented
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Control Plane Health
- [ ] PROD-CLUSTER-1 at 1.32: `gcloud container clusters describe PROD-CLUSTER-1 --region REGION --format="value(currentMasterVersion)"`
- [ ] PROD-CLUSTER-2 at 1.32: `gcloud container clusters describe PROD-CLUSTER-2 --region REGION --format="value(currentMasterVersion)"`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] GKE-managed components running (no intervention needed - Google manages nodes)

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No rejected pods due to missing resource requests: `kubectl get events -A --field-selector reason=FailedCreate`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress controllers and load balancers responding
- [ ] Application health checks passing (check your monitoring dashboards)

Autopilot-Specific Validation
- [ ] Resource requests still honored (Autopilot auto-adjusts nodes to fit)
- [ ] No workloads rejected for policy violations: `kubectl get events -A --field-selector reason=FailedCreate,reason=Rejected`
- [ ] Pod security standards enforced correctly
- [ ] Workload Identity (if used) still functioning

Observability
- [ ] Cloud Logging flowing normally
- [ ] Cloud Monitoring metrics collecting
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within acceptable range
- [ ] Resource utilization patterns normal

Business Validation
- [ ] Critical user flows tested
- [ ] Database connectivity verified
- [ ] External integrations functioning
- [ ] Performance within SLA targets

Documentation
- [ ] Upgrade completion logged in change management
- [ ] Any issues encountered documented for next upgrade cycle
- [ ] Lessons learned shared with team
```

## Key Differences for Your Autopilot Setup

**What you DON'T need to worry about:**
- Node pool surge settings (Google manages nodes automatically)
- Node capacity planning or quota management
- SSH access to nodes for debugging
- Node pool upgrade strategies (blue-green, surge, etc.)

**What's critical for Autopilot:**
- **Resource requests are mandatory** - any pod without proper CPU/memory requests will be rejected
- Your dev clusters on Rapid should have already upgraded to 1.32, giving you real-world validation
- Auto-upgrade timing is controlled via maintenance windows and exclusions (control plane only)
- All debugging must be done via `kubectl` and Cloud Logging - no node SSH access

**Recommended approach:**
1. Validate the dev cluster upgrades went smoothly (they should be on 1.32 already)
2. If you need to delay the prod upgrade, apply a maintenance exclusion before the auto-upgrade window
3. Let the auto-upgrade happen during your configured maintenance window
4. Focus post-upgrade validation on workload health and resource request compliance

Would you like me to generate specific `gcloud` commands for checking your cluster status or configuring maintenance windows?