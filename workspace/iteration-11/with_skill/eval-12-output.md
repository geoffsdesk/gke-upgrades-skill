# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Istio service mesh adds complexity to GKE upgrades, but following the correct sequence and validation steps minimizes risk. The key is **control plane first, validate mesh health, then nodes** - never upgrade both simultaneously.

## Current State Assessment

**Required Information:**
- [ ] Istio installation method: `istioctl`, Helm, or ASM (Anthos Service Mesh)?
- [ ] Current Istio version: `istioctl version` or `kubectl get pods -n istio-system`
- [ ] Mesh scope: which namespaces have sidecar injection enabled?
- [ ] Custom Istio configs: `EnvoyFilter`, `WasmPlugin`, custom gateways?

**Assumptions (please confirm):**
- Standard GKE cluster currently on 1.31.x
- Self-managed Istio (not ASM)
- Production environment requiring careful coordination

## Upgrade Sequence: Control Plane → Mesh Validation → Node Pools

### Phase 1: Pre-Upgrade Preparation

```bash
# Document current state
kubectl get nodes -o wide
istioctl version
kubectl get pods -n istio-system
kubectl get gateways,virtualservices,destinationrules -A

# Baseline mesh health
istioctl analyze -A
istioctl proxy-status
kubectl get pods -n istio-system -o wide

# Test traffic flow
curl -v https://YOUR_MESH_SERVICE/health
```

**Critical Istio-specific checks:**
- [ ] Istio version compatibility with K8s 1.32 (check [Istio support matrix](https://istio.io/latest/docs/releases/supported-releases/))
- [ ] No deprecated Istio APIs in use: `kubectl get crd | grep istio`
- [ ] Sidecar injection working: verify recent pods have Envoy containers
- [ ] Custom `EnvoyFilter` resources tested against target Istio/Envoy versions

### Phase 2: Control Plane Upgrade (GKE)

```bash
# Upgrade GKE control plane ONLY
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Wait for completion (~15 minutes)
# Verify control plane
kubectl get nodes  # Should show mixed versions (CP: 1.32, nodes: 1.31)
kubectl get pods -n kube-system | grep -v Running
```

### Phase 3: Mesh Health Validation (Critical Step)

**Do NOT proceed to node upgrades until these pass:**

```bash
# Istio control plane health
kubectl get pods -n istio-system
istioctl proxy-status  # All proxies should be SYNCED

# Traffic flow validation
istioctl analyze -A  # Should show no errors
# Test critical service paths
curl -v https://YOUR_CRITICAL_SERVICE/health

# Sidecar injection still working
kubectl delete pod SAMPLE_POD -n SAMPLE_NAMESPACE
# Verify new pod gets sidecar injection
kubectl get pods SAMPLE_POD -n SAMPLE_NAMESPACE -o jsonpath='{.spec.containers[*].name}'
```

**If any mesh validation fails, STOP. Fix Istio issues before node upgrades.**

### Phase 4: Node Pool Upgrade Strategy

For Istio workloads, **blue-green is strongly preferred over surge** to avoid split-brain mesh states:

```bash
# Configure blue-green upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade

# Or use autoscaled blue-green for better resource efficiency
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade

# Initiate upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Why blue-green for Istio?**
- Surge upgrades can create mixed Envoy proxy versions during rolling replacement
- Blue-green keeps old nodes available for fast rollback if mesh breaks
- Reduces risk of service discovery conflicts during transition

### Phase 5: Post-Node Upgrade Validation

```bash
# All nodes at target version
kubectl get nodes -o wide

# Istio proxies updated and healthy
istioctl proxy-status
kubectl get pods -n istio-system

# End-to-end traffic flow
# Test representative user journeys, not just health checks
curl -v https://YOUR_APP/api/some-endpoint

# Mesh configuration intact
kubectl get gateways,virtualservices,destinationrules -A
istioctl analyze -A
```

## Istio-Specific Gotchas & Mitigations

### 1. Sidecar Injection Breaking

**Symptom:** New pods don't get Envoy sidecars after GKE upgrade
**Root cause:** K8s API changes affecting mutating webhook
**Fix:**
```bash
# Restart Istio sidecar injector
kubectl rollout restart deployment/istiod -n istio-system
# Verify injection works
kubectl label namespace default istio-injection=enabled --overwrite
```

### 2. Custom EnvoyFilter Incompatibility

**Symptom:** Proxies show STALE or NOT_SENT status
**Root cause:** Custom `EnvoyFilter` using deprecated Envoy APIs
**Prevention:** Test all `EnvoyFilter` resources in staging first
**Fix:**
```bash
# Identify problematic filters
kubectl get envoyfilters -A
istioctl proxy-config dump POD_NAME -n NAMESPACE | grep -i error
```

### 3. Certificate/TLS Issues

**Symptom:** mTLS failing between services after upgrade
**Root cause:** Istio CA or cert-manager compatibility
**Mitigation:**
```bash
# Check certificate health
kubectl get secrets -n istio-system | grep cacerts
istioctl proxy-config secret POD_NAME -n NAMESPACE
```

### 4. Service Discovery Lag

**Symptom:** 503 errors during node replacement
**Root cause:** Pilot sync lag to new Envoy instances
**Mitigation:** Use blue-green upgrades with longer soak time

## Rollback Strategy

If mesh breaks after node upgrades:

```bash
# Fast rollback via blue-green
kubectl uncordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME
kubectl cordon -l cloud.google.com/gke-nodepool=NEW_POOL_NAME

# Force pod rescheduling to old nodes
kubectl delete pods -n PRODUCTION_NAMESPACE --all
```

For control plane issues: contact GKE support for potential downgrade.

## Pre-Upgrade Checklist

```markdown
- [ ] Istio version compatibility confirmed with K8s 1.32
- [ ] Staging environment upgraded and tested end-to-end
- [ ] Custom EnvoyFilter resources validated
- [ ] Traffic management rules documented and tested
- [ ] Monitoring dashboards for mesh metrics active
- [ ] Blue-green node pool upgrade strategy confirmed
- [ ] Rollback procedures tested in staging
- [ ] Critical service endpoints identified for post-upgrade testing
- [ ] On-call team briefed on mesh-specific failure modes
```

## Monitoring During Upgrade

**Key metrics to watch:**
- Istio proxy status: `istioctl proxy-status`
- Service mesh error rates: check Kiali/Grafana dashboards
- Certificate expiry: `kubectl get secrets -n istio-system`
- Gateway connectivity: external traffic ingress
- East-west traffic: inter-service communication latency

**Would you like me to adapt this plan based on your specific Istio version and setup, or dive deeper into any particular phase?**