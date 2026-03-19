# GKE + Istio Upgrade Plan: 1.29 → 1.30

Given the complexity of service mesh upgrades, here's a comprehensive plan that addresses the order of operations and common failure points.

## Context Assessment

- **Cluster mode**: Standard GKE
- **Current version**: 1.29.x → **Target**: 1.30.x  
- **Istio deployment**: Need to confirm your setup (see pre-flight checks)
- **Risk profile**: High - service mesh upgrades have multiple failure modes

## Critical Order of Operations

The sequence matters enormously with Istio. Getting this wrong is the #1 cause of mesh upgrade failures:

### Phase 1: Istio Control Plane First
1. **Upgrade Istio control plane** to a version compatible with GKE 1.30
2. **Verify mesh connectivity** - run full smoke tests
3. **Soak for 24-48 hours** - catch any subtle control plane issues

### Phase 2: GKE Control Plane  
4. **Upgrade GKE control plane** to 1.30.x
5. **Verify Istio components still healthy** on new Kubernetes version

### Phase 3: Node Pools (Most Dangerous)
6. **Upgrade node pools** with conservative surge settings
7. **Monitor sidecar injection** as pods reschedule
8. **Validate mesh traffic flow** after each node pool

## Pre-Flight Checks

Before starting, establish your current Istio setup:

```bash
# Istio version and components
kubectl get pods -n istio-system
istioctl version

# Installation method (affects upgrade path)
kubectl get istiooperators -n istio-system  # Istio Operator
kubectl get managedcertificates -n istio-system  # ASM (Google-managed)
helm list -n istio-system  # Helm

# Traffic management complexity
kubectl get virtualservices,destinationrules,gateways -A
kubectl get pods -l istio-injection=enabled -A | wc -l  # Sidecar count

# External dependencies  
kubectl get gateways -A -o yaml | grep -i "cloud\.google\.com"  # GKE Ingress integration
```

## Istio Version Compatibility Matrix

**Critical**: Istio has specific GKE version support windows. Using an incompatible combination breaks the mesh entirely.

| GKE Version | Supported Istio Versions | Recommended |
|-------------|-------------------------|-------------|
| 1.29.x | 1.17.x - 1.20.x | **1.20.x** (latest) |
| 1.30.x | 1.18.x - 1.21.x | **1.21.x** (latest) |

**Your upgrade path**: Istio 1.20.x → 1.21.x, then GKE 1.29 → 1.30.

Check current compatibility:
```bash
istioctl x precheck
```

## Phase 1: Istio Control Plane Upgrade

### ASM (Anthos Service Mesh) - Google Managed
If you're using ASM, Google handles control plane upgrades:

```bash
# Check current ASM version
kubectl get controlplanerevision -n istio-system

# Upgrade to compatible revision
gcloud container fleet mesh update \
  --control-plane automatic \
  --membership MEMBERSHIP_NAME
```

### Self-Managed Istio
**Canary upgrade approach** (safest for production):

```bash
# Install new Istio version alongside existing
istioctl install --set revision=1-21-0 --set values.pilot.env.EXTERNAL_ISTIOD=false

# Verify both control planes running
kubectl get pods -n istio-system

# Gradually migrate namespaces
kubectl label namespace NAMESPACE istio.io/rev=1-21-0 istio-injection-
kubectl rollout restart deployment -n NAMESPACE

# Validate traffic flow before proceeding
```

**Watch for these control plane issues:**
- Istiod pods in CrashLoopBackOff
- Webhook admission failures (check for PVCs being rejected)
- Certificate rotation problems
- Cross-cluster communication breaks (if using multi-cluster mesh)

## Phase 2: GKE Control Plane Upgrade

```bash
# Upgrade GKE control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.x-gke.LATEST

# Critical validation after CP upgrade
kubectl get pods -n istio-system  # All istiod pods healthy?
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio
istioctl proxy-status  # All proxies connected?
```

**Common control plane upgrade failures:**
- **Webhook timeouts**: New K8s API server can't reach istiod webhooks during startup
- **RBAC changes**: K8s 1.30 may have tightened permissions that break Istio components  
- **CRD version skew**: Istio CRDs may be incompatible with K8s 1.30

## Phase 3: Node Pool Upgrades (Highest Risk)

This is where most mesh upgrades fail. Every pod restart triggers sidecar re-injection.

### Conservative surge settings for mesh workloads:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why conservative?** 
- Sidecar injection happens during pod startup
- If injection webhook is unhealthy, pods fail to schedule
- Mesh connectivity issues aren't apparent until traffic flows

### Node upgrade monitoring:
```bash
# Watch for injection failures
kubectl get events -A --field-selector reason=FailedCreate

# Monitor sidecar health during rolling restart
watch 'kubectl get pods -A -o wide | grep -E "(istio-proxy|Pending|Error)"'

# Validate mesh connectivity per batch
istioctl proxy-status
kubectl exec -it POD_NAME -c istio-proxy -- pilot-agent request GET /stats/prometheus | grep cluster_manager
```

## Mesh-Specific Failure Modes

### 1. Sidecar injection webhook failures
**Symptom**: Pods stuck in Pending, events show webhook timeouts
**Fix**: 
```bash
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml
# Look for failurePolicy: Fail (dangerous) vs Ignore (safer)

# Temporary fix - allow pods without sidecars
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

### 2. Certificate rotation during upgrade
**Symptom**: mTLS failures, 503 errors between services
**Fix**:
```bash
# Check cert status
istioctl proxy-config secret POD_NAME

# Force cert refresh
istioctl proxy-config cluster POD_NAME --fqdn outbound_.443_._.kubernetes.default.svc.cluster.local
```

### 3. Traffic policy conflicts
**Symptom**: Some service-to-service calls fail after node restart
**Root cause**: VirtualServices/DestinationRules may reference old node IPs or have version-specific configs

```bash
kubectl get virtualservices,destinationrules -A -o yaml | grep -i version
```

### 4. Gateway/Ingress controller issues  
**Symptom**: External traffic can't reach the cluster
**Check**: 
```bash
kubectl get gateways -A
kubectl get pods -n istio-system -l istio=ingressgateway
kubectl get svc -n istio-system istio-ingressgateway
```

## Validation Runbook

After each phase, run this validation sequence:

```bash
# 1. Control plane health
kubectl get pods -n istio-system
istioctl version

# 2. Data plane connectivity  
istioctl proxy-status
kubectl exec -it POD_NAME -c istio-proxy -- curl localhost:15000/clusters

# 3. End-to-end traffic
# Deploy httpbin test workload if not already present
kubectl apply -f https://raw.githubusercontent.com/istio/istio/master/samples/httpbin/httpbin.yaml
kubectl exec -it sleep-POD -- curl httpbin:8000/get

# 4. External ingress (if using Istio Gateway)
curl -H "Host: YOURDOMAIN" http://EXTERNAL_IP/

# 5. Mesh metrics and tracing
kubectl port-forward -n istio-system svc/prometheus 9090:9090
# Check for unusual error rates in Prometheus
```

## Rollback Strategy

**Control plane rollback** (if Istio upgrade fails):
```bash
# Switch back to old revision
kubectl label namespace NAMESPACE istio.io/rev=1-20-0 istio.io/rev-

# Remove failed revision
istioctl uninstall --revision 1-21-0
```

**Node pool rollback** (if injection fails):
```bash
# Create new node pool at old GKE version
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.x-gke.VERSION

# Migrate workloads back
kubectl cordon -l cloud.google.com/gke-nodepool=NEW_POOL_NAME
```

## Timeline and Risk Mitigation

**Recommended timeline:**
- **Week 1**: Istio control plane upgrade + soak
- **Week 2**: GKE control plane upgrade + validation  
- **Week 3**: Node pool upgrades (one pool per day maximum)

**Risk mitigation:**
- Test the entire sequence in staging first
- Have dedicated mesh expertise on-call during the upgrade
- Consider upgrading non-critical node pools first (monitoring, logging) before app workloads
- Keep old Istio revision running until fully validated

The "horror stories" you've heard are real, but they're almost always from rushing the sequence or skipping the control plane soak period. Take your time with this upgrade.