# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Service mesh upgrades require careful sequencing to avoid breaking traffic routing and security policies. The key insight: **upgrade GKE control plane first, validate mesh compatibility, then proceed with node pools**. Istio's admission webhooks and API dependencies are the primary risk areas.

## Upgrade Sequence

### Phase 1: Pre-upgrade Validation
**Before touching anything**, verify Istio compatibility:

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio 1.x supports Kubernetes 1.32
# Check Istio release notes for K8s 1.32 compatibility matrix
```

**Critical checkpoint:** Ensure your Istio version officially supports Kubernetes 1.32. If not, you'll need to upgrade Istio first (separate operation).

### Phase 2: Control Plane Upgrade
```bash
# Upgrade control plane only (NOT nodes yet)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx
```

**Why control plane first:** Istio's admission webhooks must validate against the new API server version. If webhooks fail, pod creation breaks cluster-wide.

### Phase 3: Istio Webhook Validation
Immediately after control plane upgrade:

```bash
# Test webhook functionality
kubectl run istio-test --image=nginx --rm -it --restart=Never -- echo "webhook test"

# Check for webhook errors in events
kubectl get events -A --field-selector type=Warning | grep -i "webhook\|admission"

# Verify sidecar injection still works
kubectl label namespace default istio-injection=enabled --overwrite
kubectl run sidecar-test --image=nginx --dry-run=server -o yaml | grep -A5 -B5 istio
```

**If webhook validation fails:**
```bash
# Temporarily set webhook to ignore failures
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"config.validation.istio.io","failurePolicy":"Ignore"}]}'

# Check Istio control plane health
kubectl get pods -n istio-system
kubectl logs -n istio-system deployment/istiod --tail=50
```

### Phase 4: Node Pool Upgrade Strategy
**Recommended for service mesh: Autoscaled Blue-Green**

Standard surge upgrades cause inference latency spikes as pods restart. Autoscaled blue-green keeps the old pool serving while the new pool warms up:

```bash
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 3 --total-max-nodes 20 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Why autoscaled blue-green for mesh:**
- Avoids inference downtime from pod restarts
- Gives time for Envoy sidecars to warm up on new nodes
- Preserves service mesh topology during transition

### Phase 5: Post-Upgrade Mesh Validation

```bash
# Verify all mesh components healthy
kubectl get pods -n istio-system
kubectl get crd | grep istio

# Test service-to-service communication
kubectl exec -it POD_NAME -c CONTAINER_NAME -- curl SERVICE_NAME:PORT/health

# Check for any mesh configuration drift
istioctl proxy-config cluster POD_NAME.NAMESPACE
istioctl analyze -A
```

## Critical Watch Points

### 1. Admission Webhook Failures
**Symptom:** Pods fail to create with "admission webhook denied the request"

**Root cause:** Istio's validating webhook (`config.validation.istio.io`) rejects configurations on the new API version

**Fix:**
```bash
# Check webhook configuration
kubectl describe validatingwebhookconfigurations istio-validator-istio-system

# If webhook is incompatible, temporarily disable
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"config.validation.istio.io","failurePolicy":"Ignore"}]}'

# Upgrade Istio control plane to compatible version
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false
```

### 2. Sidecar Injection Breaking
**Symptom:** New pods don't get Envoy sidecars injected

**Diagnosis:**
```bash
# Check mutating webhook health
kubectl describe mutatingwebhookconfigurations istio-sidecar-injector

# Verify injection namespace labels
kubectl get namespace -L istio-injection
```

### 3. Network Policy Semantic Changes
Kubernetes 1.32 may have NetworkPolicy behavior changes that affect Istio's security model:

```bash
# Test NetworkPolicy enforcement
kubectl get networkpolicies -A
# Run connectivity tests between services
```

### 4. Certificate/TLS Issues
**Symptom:** mTLS failures between services post-upgrade

**Check:**
```bash
# Verify Istio root CA health
kubectl get secret cacerts -n istio-system
kubectl get configmap istio-ca-root-cert -n istio-system

# Check certificate rotation
istioctl proxy-config secret POD_NAME.NAMESPACE | grep ROOTCA
```

## Mesh-Specific Pre-Upgrade Checklist

```markdown
Istio + GKE Upgrade Checklist
- [ ] Current Istio version: ___
- [ ] Istio officially supports Kubernetes 1.32 (check compatibility matrix)
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] No deprecated APIs in Istio CRDs: `istioctl analyze -A`
- [ ] Baseline service-to-service connectivity documented
- [ ] Service mesh monitoring active (Kiali/Jaeger if used)
- [ ] mTLS certificate expiration dates checked
- [ ] Envoy proxy versions compatible with target node image
- [ ] Network policies tested in dev environment
```

## Rollback Strategy

If the upgrade breaks mesh functionality:

1. **Control plane rollback:** Contact GKE support (control plane minor downgrades require assistance)
2. **Node pool rollback:** Create new node pool at 1.31, migrate workloads
3. **Istio rollback:** `istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --revision PREVIOUS_VERSION`

## Alternative: Istio Canary Upgrade Pattern

For maximum safety, consider upgrading Istio using canary deployments:

1. Install new Istio version alongside current (`--revision canary`)
2. Migrate select workloads to canary Istio
3. Validate mesh functionality on canary
4. Complete Istio upgrade
5. Then upgrade GKE

This approach isolates Istio upgrade risk from GKE upgrade risk.

## Timeline Estimate

- **Control plane:** 10-15 minutes
- **Webhook validation:** 15-30 minutes
- **Node pool (autoscaled blue-green):** 2-4 hours depending on cluster size
- **Total maintenance window:** 4-6 hours for safety

The mesh adds complexity but this sequence minimizes blast radius. The key is validating webhook compatibility immediately after the control plane upgrade, before proceeding to nodes.