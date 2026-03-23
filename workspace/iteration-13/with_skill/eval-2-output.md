# GKE Autopilot Upgrade Checklists

**Environment:** 4 Autopilot clusters | Dev: Rapid channel | Prod: Stable channel  
**Upgrade:** 1.31 → 1.32 (minor version upgrade)  
**Timeline:** Next month (auto-upgrade)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Clusters (1.31 → 1.32)
- [ ] Clusters: 2 dev (Rapid) + 2 prod (Stable) | All Autopilot mode

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] No deprecated API usage detected:
      - Check GKE deprecation insights in Cloud Console
      - Run: kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
- [ ] Third-party operators/controllers tested against 1.32 in dev clusters
- [ ] Admission webhooks validated against 1.32 API changes
- [ ] Container images compatible with Kubernetes 1.32

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests (CPU/memory) - mandatory for Autopilot
      Check: kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].resources.requests}{"\n"}{end}' | grep -v "cpu\|memory"
- [ ] PDBs configured for critical workloads (not overly restrictive)
      Review: kubectl get pdb -A -o wide
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets
      Check: kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
- [ ] terminationGracePeriodSeconds appropriate (≤30s recommended for Autopilot)
- [ ] StatefulSet data backed up, PV reclaim policies verified

Auto-Upgrade Controls
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
      Verify: gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(maintenancePolicy)"
- [ ] Consider maintenance exclusion if upgrade timing needs adjustment:
      - "No upgrades" (30-day max, blocks everything)
      - "No minor upgrades" (up to EoS, allows patches only)
- [ ] Auto-upgrade timing confirmed acceptable for next month
      Check: gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

Dev Environment Validation (Rapid channel clusters likely already upgraded)
- [ ] Dev clusters already on 1.32? Verify: gcloud container clusters list --format="table(name,currentMasterVersion)"
- [ ] If dev on 1.32: application testing completed successfully
- [ ] Performance/functionality regression testing passed in dev
- [ ] Integration tests passing against 1.32

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput)
- [ ] Upgrade notifications configured (Cloud Logging, Pub/Sub)
- [ ] On-call team aware of upcoming auto-upgrades
- [ ] Rollback plan documented (limited options for control plane - mainly workload-level)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot Clusters (1.32)

Control Plane Health
- [ ] All clusters at 1.32: gcloud container clusters list --format="table(name,currentMasterVersion)"
- [ ] System pods healthy: kubectl get pods -n kube-system
- [ ] GKE managed components operational: kubectl get pods -n gke-system
- [ ] API server responsive: kubectl get --raw /healthz

Workload Health
- [ ] All deployments at desired replica count: kubectl get deployments -A
- [ ] No failed pods: kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
- [ ] StatefulSets fully ready: kubectl get statefulsets -A
- [ ] No stuck PDBs: kubectl get pdb -A -o wide
- [ ] Autopilot node provisioning working: kubectl get nodes (should auto-scale as needed)

Application Validation
- [ ] Application health checks passing
- [ ] Ingress/load balancers responding correctly
- [ ] Internal service discovery working (DNS)
- [ ] External integrations functional
- [ ] Smoke tests completed for critical user journeys

Observability & Metrics
- [ ] Cloud Logging ingestion normal
- [ ] Metrics pipeline active, no collection gaps
- [ ] Error rates within pre-upgrade baseline
- [ ] Response latency (p50/p95/p99) within acceptable range
- [ ] Custom metrics and dashboards functional

Autopilot-Specific Checks
- [ ] Pod resource requests still being honored correctly
- [ ] Node auto-provisioning responding to workload changes
- [ ] GKE managed certificates renewed if applicable: kubectl get managedcertificates -A
- [ ] Autopilot-specific annotations still working on pods/services

Documentation & Cleanup
- [ ] Upgrade completion logged in runbook/changelog
- [ ] Remove any temporary maintenance exclusions applied
- [ ] Update environment documentation with new version
- [ ] Schedule next upgrade planning (1.32 → 1.33 in ~3 months)
```

## Key Autopilot Considerations

Since you're running Autopilot clusters:

1. **No node pool management needed** - Google handles all node lifecycle
2. **Resource requests are mandatory** - Any pod without CPU/memory requests will be rejected
3. **Limited customization** - Focus on workload readiness rather than infrastructure tuning  
4. **Auto-scaling built-in** - Nodes provision automatically based on workload demand

## Recommended Timeline

- **2 weeks before:** Complete pre-upgrade checklist
- **1 week before:** Validate dev clusters (likely already upgraded to 1.32)
- **Day of upgrade:** Monitor during maintenance window
- **Day after:** Complete post-upgrade validation

Your dev clusters on Rapid channel have likely already been upgraded to 1.32, giving you a head start on testing!