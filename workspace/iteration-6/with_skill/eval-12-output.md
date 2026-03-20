# GKE + Istio Upgrade Plan: 1.29 → 1.30

You're right to be cautious — service mesh upgrades have additional complexity. Here's a structured plan to minimize risk.

## Context Assessment

**Cluster:** Standard GKE  
**Current:** 1.29  
**Target:** 1.30  
**Service Mesh:** Istio  

**Key considerations:**
- Istio has strict Kubernetes version compatibility requirements
- Control plane and data plane must be upgraded in sequence
- Envoy proxy versions are coupled to Istio releases
- Traffic routing can break during proxy restarts

## Upgrade Order (Critical)

The sequence matters for mesh stability:

1. **Istio control plane** (istiod)
2. **GKE control plane** 
3. **GKE node pools**
4. **Istio data plane** (sidecars)

Never upgrade GKE beyond what your Istio version supports.

## Pre-Upgrade Checklist

```markdown
Istio Compatibility
- [ ] Current Istio version: ___
- [ ] Istio 1.30+ support verified (check Istio release notes)
- [ ] If unsupported: plan Istio upgrade first to compatible version
- [ ] Istio operator/installation method documented: ___ (istioctl / Helm / Operator)

Mesh Health Baseline
- [ ] All Istio components healthy: `kubectl get pods -n istio-system`
- [ ] Envoy proxy status: `istioctl proxy-status`
- [ ] No proxy version skew: `istioctl version`
- [ ] Traffic policies working: test ingress gateway, virtual services
- [ ] mTLS status verified: `istioctl authn tls-check`
- [ ] Current mesh metrics captured (request rates, success rates, latency)

Workload Readiness (Standard GKE items)
- [ ] PDBs configured for critical services
- [ ] No bare pods
- [ ] Adequate termination grace periods (30s+ for mesh workloads)
- [ ] Node pool surge strategy: maxSurge=1, maxUnavailable=0 (conservative for mesh)

Risk Mitigation
- [ ] Test upgrade on staging cluster with identical Istio setup
- [ ] Canary deployment strategy ready for critical services
- [ ] Service mesh bypass plan documented (remove sidecar injection temporarily)
- [ ] Traffic splitting/failover to non-mesh services available if needed
```

## Step-by-Step Runbook

### Phase 1: Istio Control Plane Upgrade (if needed)

```bash
# Check current Istio version
istioctl version

# If Istio < 1.18, upgrade Istio first to support K8s 1.30
# Follow Istio canary upgrade process
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --set values.istiodRemote.enabled=false
```

**Validation:**
```bash
kubectl get pods -n istio-system
istioctl proxy-status
# Should show control plane healthy, data plane may show version skew (expected)
```

### Phase 2: GKE Control Plane Upgrade

```bash
# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.X-gke.XXX

# Wait for completion (~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Validation:**
```bash
kubectl get pods -n kube-system
kubectl get pods -n istio-system
# Istio should still be healthy
istioctl proxy-status | head -20
```

### Phase 3: GKE Node Pool Upgrade

**Configure conservative surge settings for mesh stability:**
```bash
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Upgrade node pools one at a time:**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXX
```

**Monitor mesh during node upgrades:**
```bash
# Watch proxy reconnections
watch 'istioctl proxy-status | grep -v SYNCED | wc -l'

# Monitor service connectivity
kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
curl -I http://INGRESS_IP/your-health-endpoint
```

### Phase 4: Istio Data Plane Upgrade

After all nodes are upgraded, update sidecar proxies:

```bash
# Rolling restart of workloads to pick up new Envoy version
kubectl rollout restart deployment -n NAMESPACE DEPLOYMENT_NAME

# Or restart all deployments in a namespace
kubectl get deployments -n NAMESPACE -o name | xargs kubectl rollout restart -n NAMESPACE

# Monitor rollout
kubectl rollout status deployment -n NAMESPACE DEPLOYMENT_NAME
```

## Istio-Specific Risks & Mitigations

### 1. Envoy Proxy Version Compatibility
**Risk:** New node images may have incompatible Envoy versions  
**Mitigation:** Test in staging first, verify `istioctl version` shows compatible proxy versions

### 2. Certificate Renewal Issues
**Risk:** mTLS certificates may not renew properly during upgrade  
**Mitigation:** 
```bash
# Check cert expiry before upgrade
istioctl proxy-config secret -n NAMESPACE POD_NAME

# Force cert renewal if needed
kubectl delete secret -n istio-system cacerts
```

### 3. Traffic Routing Disruption
**Risk:** Virtual services, destination rules may behave differently  
**Mitigation:** 
```bash
# Validate routing rules
istioctl analyze -n NAMESPACE

# Check traffic distribution
istioctl proxy-config routes GATEWAY_POD.istio-system
```

### 4. Admission Webhook Failures
**Risk:** Istio's sidecar injector webhook may reject pods during upgrade  
**Mitigation:**
```bash
# Check webhook status
kubectl get validatingwebhookconfigurations istio-validator-istio-system

# Temporarily disable if blocking (last resort)
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"rev.validation.istio.io","failurePolicy":"Ignore"}]}'
```

## Troubleshooting Common Istio Upgrade Issues

### Proxy Status Shows "NOT SENT"
```bash
istioctl proxy-status
# If proxies show NOT SENT, restart istiod
kubectl rollout restart deployment/istiod -n istio-system
```

### Sidecar Injection Stops Working
```bash
# Check injection webhook
kubectl get mutatingwebhookconfigurations istio-sidecar-injector

# Verify namespace labeling
kubectl get namespace NAMESPACE -o yaml | grep istio-injection
```

### mTLS Failures After Upgrade
```bash
# Check TLS configuration
istioctl authn tls-check SERVICE_NAME.NAMESPACE.svc.cluster.local

# Restart workloads to refresh certificates
kubectl rollout restart deployment -n NAMESPACE DEPLOYMENT_NAME
```

## Post-Upgrade Validation

```markdown
GKE Health
- [ ] Control plane at 1.30: `gcloud container clusters describe`
- [ ] All nodes at 1.30: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`

Istio Mesh Health  
- [ ] All Istio components running: `kubectl get pods -n istio-system`
- [ ] Proxy status clean: `istioctl proxy-status | grep -v SYNCED | wc -l` (should be 0)
- [ ] Version alignment: `istioctl version` (control plane and data plane match)
- [ ] mTLS working: `istioctl authn tls-check`
- [ ] Gateway responding: test ingress endpoints
- [ ] Internal service-to-service communication working

Traffic & Performance
- [ ] Request success rates match pre-upgrade baseline
- [ ] Latency (p50/p95) within acceptable range  
- [ ] No certificate expiry warnings
- [ ] Traffic policies (circuit breakers, retries) functioning
- [ ] Observability (Jaeger, Kiali) showing healthy traces
```

## Emergency Rollback Plan

If mesh breaks critically:

1. **Temporarily disable sidecar injection:**
```bash
kubectl label namespace NAMESPACE istio-injection-
kubectl rollout restart deployment -n NAMESPACE DEPLOYMENT_NAME
```

2. **Route traffic around mesh:** Update ingress to point directly to services
3. **For GKE rollback:** Create new node pool at 1.29, migrate workloads

The key is maintaining service availability even if mesh features temporarily degrade.

**Next steps:** Test this sequence on a staging cluster that mirrors your production Istio setup before attempting on production.