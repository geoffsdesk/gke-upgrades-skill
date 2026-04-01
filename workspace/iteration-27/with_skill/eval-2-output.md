# GKE Autopilot Upgrade Checklists
**Setup:** 4 Autopilot clusters | Dev: 2 clusters (Rapid) | Prod: 2 clusters (Stable) | Upgrade: 1.31 → 1.32

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Dev clusters: _____ | Prod clusters: _____
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] No deprecated API usage detected:
      - [ ] Check GKE deprecation insights dashboard (Console → Insights tab)
      - [ ] Run: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Third-party operators compatible with K8s 1.32:
      - [ ] Ingress controllers (nginx, istio, etc.)
      - [ ] Monitoring (Prometheus operator, etc.)
      - [ ] CI/CD operators (ArgoCD, Tekton, etc.)
      - [ ] Security tools (Falco, OPA Gatekeeper, etc.)

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests (mandatory - pods will be rejected without them):
      ```bash
      kubectl get pods -A -o json | jq -r '.items[] | select(.spec.containers[]? | .resources.requests == null) | "\(.metadata.namespace)/\(.metadata.name)"'
      ```
- [ ] PDBs configured for critical workloads (but not overly restrictive):
      ```bash
      kubectl get pdb -A -o wide
      # Verify ALLOWED DISRUPTIONS > 0 for each PDB
      ```
- [ ] No bare pods - all managed by controllers:
      ```bash
      kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
      ```
- [ ] terminationGracePeriodSeconds ≤ 600s (10min limit for most pods, 25s for Spot):
      ```bash
      kubectl get pods -A -o json | jq '.items[] | select(.spec.terminationGracePeriodSeconds > 600) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
      ```

Channel Strategy Validation
- [ ] Dev clusters on Rapid channel have already received 1.32 (natural progression)
- [ ] Dev validation completed successfully on 1.32
- [ ] Prod clusters on Stable channel will auto-upgrade after Rapid → Regular → Stable progression
- [ ] Consider: Do you want manual control over timing, or let auto-upgrade proceed?
      - [ ] Option A: Let auto-upgrade proceed during configured maintenance windows
      - [ ] Option B: Apply temporary "no upgrades" exclusion, then manually trigger when ready

Maintenance Controls (if manual timing desired)
- [ ] Maintenance windows configured for off-peak hours:
      ```bash
      gcloud container clusters describe CLUSTER_NAME --location LOCATION --format="value(maintenancePolicy)"
      ```
- [ ] Temporary exclusion planned if deferring auto-upgrade:
      ```bash
      # Example: 30-day max exclusion
      gcloud container clusters update PROD_CLUSTER_1 \
        --location LOCATION \
        --add-maintenance-exclusion-name "control-1-32-timing" \
        --add-maintenance-exclusion-start-time 2024-MM-DDTHH:00:00Z \
        --add-maintenance-exclusion-end-time 2024-MM-DDTHH:00:00Z \
        --add-maintenance-exclusion-scope no_upgrades
      ```

Observability & Ops Readiness
- [ ] Baseline metrics captured (error rates, latency, throughput)
- [ ] Cloud Monitoring alerts active and functional
- [ ] Cloud Logging collection verified
- [ ] Upgrade notifications configured (scheduled notifications opt-in):
      ```bash
      gcloud container clusters update CLUSTER_NAME --location LOCATION --enable-scheduled-upgrades
      ```
- [ ] On-call team aware of upgrade timeline
- [ ] Stakeholders notified of maintenance window

Testing Strategy
- [ ] Dev clusters (Rapid) serve as canaries - 1.32 already deployed there
- [ ] Dev workload validation completed on 1.32
- [ ] Critical user journeys tested in dev environment
- [ ] Performance baseline comparison (dev 1.31 vs 1.32) completed
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Control Plane Health
- [ ] Prod cluster 1: Control plane version 1.32
      ```bash
      gcloud container clusters describe PROD_CLUSTER_1 --location LOCATION --format="value(currentMasterVersion)"
      ```
- [ ] Prod cluster 2: Control plane version 1.32
      ```bash  
      gcloud container clusters describe PROD_CLUSTER_2 --location LOCATION --format="value(currentMasterVersion)"
      ```
- [ ] All nodes showing Ready status:
      ```bash
      kubectl get nodes --context PROD_CLUSTER_1_CONTEXT
      kubectl get nodes --context PROD_CLUSTER_2_CONTEXT
      ```
- [ ] System pods healthy in kube-system namespace:
      ```bash
      kubectl get pods -n kube-system --context PROD_CLUSTER_1_CONTEXT
      kubectl get pods -n kube-system --context PROD_CLUSTER_2_CONTEXT
      ```

Workload Health Validation
- [ ] All deployments at desired replica count:
      ```bash
      kubectl get deployments -A --context PROD_CLUSTER_1_CONTEXT
      kubectl get deployments -A --context PROD_CLUSTER_2_CONTEXT
      ```
- [ ] No pods in CrashLoopBackOff or extended Pending:
      ```bash
      kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --context PROD_CLUSTER_1_CONTEXT
      kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --context PROD_CLUSTER_2_CONTEXT
      ```
- [ ] StatefulSets fully ready and at target replicas:
      ```bash
      kubectl get statefulsets -A --context PROD_CLUSTER_1_CONTEXT
      kubectl get statefulsets -A --context PROD_CLUSTER_2_CONTEXT
      ```
- [ ] Ingress controllers responding:
      - [ ] Test external load balancers and ingress endpoints
      - [ ] Verify SSL/TLS certificates valid
- [ ] Application-specific health checks passing

API and Admission Webhook Validation
- [ ] No admission webhook failures:
      ```bash
      kubectl get events -A --field-selector type=Warning | grep webhook
      ```
- [ ] Cert-manager (if present) issuing certificates correctly:
      ```bash
      kubectl get certificates -A
      kubectl get certificaterequests -A
      ```
- [ ] Service mesh control plane healthy (if Istio/ASM deployed):
      ```bash
      kubectl get pods -n istio-system  # or asm-system
      ```

Performance and Observability
- [ ] Monitoring pipeline active - no collection gaps:
      - [ ] Cloud Monitoring metrics flowing
      - [ ] Custom Prometheus metrics (if any) collecting
- [ ] Cloud Logging ingestion normal:
      ```bash
      # Check for recent logs in Cloud Console or via gcloud
      gcloud logging read "resource.type=k8s_cluster resource.labels.cluster_name=CLUSTER_NAME" --limit=10
      ```
- [ ] Application performance within baseline:
      - [ ] API response times (p50/p95/p99) normal
      - [ ] Error rates within expected thresholds
      - [ ] Throughput/QPS comparable to pre-upgrade

Business Function Verification  
- [ ] Critical user journeys tested in production
- [ ] Database connectivity and query performance normal
- [ ] External API integrations functioning
- [ ] Background job processing continuing
- [ ] File uploads/downloads working

Cleanup and Documentation
- [ ] Remove temporary maintenance exclusions (if applied):
      ```bash
      gcloud container clusters update PROD_CLUSTER_1 \
        --location LOCATION \
        --remove-maintenance-exclusion "control-1-32-timing"
      ```
- [ ] Upgrade success documented in change log
- [ ] Performance comparison (1.31 vs 1.32) documented
- [ ] Lessons learned captured for future upgrades
- [ ] Team retrospective scheduled (what went well, what to improve)

Next Steps
- [ ] Monitor for 48-72 hours post-upgrade
- [ ] Plan next upgrade cadence review (channel strategy working well?)
- [ ] Update runbooks with any new 1.32-specific considerations
```

## Key Notes for Your Environment

**Channel Strategy:** Your current setup (dev=Rapid, prod=Stable) provides natural progression testing. Dev clusters get 1.32 first, giving you ~4-6 weeks to validate before prod receives it. This is a solid canary strategy.

**Auto-upgrade vs Manual Control:** Since you received upgrade notifications, these will be auto-upgrades during your maintenance windows unless you apply exclusions. Most Autopilot customers let auto-upgrades proceed since node management is handled by Google.

**Autopilot-Specific Considerations:**
- Resource requests are mandatory - pods without them will be rejected
- No SSH access to nodes - use `kubectl debug` and Cloud Logging for troubleshooting  
- PDB timeout is 10 minutes max (25 seconds for Spot pods)
- All clusters are regional - control plane stays available during upgrades

**Maintenance Exclusions:** Only use "no upgrades" exclusions if you need to control the exact timing. These are limited to 30 days max. For routine upgrades like this, maintenance windows alone usually provide sufficient control.