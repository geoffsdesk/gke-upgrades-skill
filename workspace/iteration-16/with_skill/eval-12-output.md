# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Istio service mesh adds complexity to GKE upgrades due to admission webhooks, sidecar injection, and networking policies. The key is **upgrading Istio first** to ensure compatibility with Kubernetes 1.32, then upgrading GKE with careful attention to webhook behavior and sidecar readiness.

## Critical Compatibility Check

**First step:** Verify your current Istio version supports Kubernetes 1.32. Check the [Istio supported platforms matrix](https://istio.io/latest/docs/releases/supported-releases/#support-status-of-istio-releases).

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'
istioctl version

# Required: Istio 1.19+ for Kubernetes 1.32 support
```

If your Istio version doesn't support K8s 1.32, **upgrade Istio first** before touching GKE.

## Upgrade Sequence

### Phase 1: Istio Control Plane Upgrade (if needed)

```bash
# 1. Download compatible Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.20.2 sh -
cd istio-1.20.2
export PATH=$PWD/bin:$PATH

# 2. Upgrade Istio control plane (canary method recommended)
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --set revision=1-20-2

# 3. Verify control plane health
kubectl get pods -n istio-system
istioctl proxy-status

# 4. Update webhook configurations for new revision
# (This varies by setup - check your Istio installation method)
```

### Phase 2: GKE Control Plane Upgrade

```bash
# 1. Pre-flight webhook check
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# 2. Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.y

# 3. Validate immediately after CP upgrade
kubectl get pods -n istio-system
kubectl get validatingwebhookconfigurations istiod-default-validator -o yaml | grep clientConfig
```

### Phase 3: Node Pool Upgrade Strategy

**Recommended approach:** Conservative surge with webhook monitoring

```bash
# Configure conservative surge settings
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Start node upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y
```

## Critical Monitoring During Upgrade

### 1. Webhook Health (most critical)

```bash
# Monitor webhook rejections in real-time
kubectl get events -A --field-selector type=Warning --watch | grep webhook

# Check webhook endpoint connectivity
kubectl get validatingwebhookconfigurations istiod-default-validator \
  -o jsonpath='{.webhooks[0].clientConfig.service}'

# Test webhook response
kubectl run test-pod --image=nginx --dry-run=server -o yaml
```

### 2. Sidecar Injection Status

```bash
# Monitor pods without sidecars (should decrease during upgrade)
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}' | grep -v istio-proxy

# Check injection webhook
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml

# Verify namespace labels
kubectl get namespaces -l istio-injection=enabled
```

### 3. Istio Proxy Readiness

```bash
# Check proxy status across cluster
istioctl proxy-status

# Monitor sidecar startup on new nodes
kubectl get pods -A -o wide | grep -E "ContainerCreating|Init"

# Check for proxy config sync issues
istioctl proxy-config cluster PROXY_NAME.NAMESPACE
```

## Common Failure Scenarios & Fixes

### 1. Webhook Certificate Issues

**Symptoms:** Pods fail to create with "admission webhook rejected the request"

**Immediate fix:**
```bash
# Temporarily set webhook failure policy to Ignore
kubectl patch validatingwebhookconfigurations istiod-default-validator \
  -p '{"webhooks":[{"name":"validation.istio.io","failurePolicy":"Ignore"}]}'

# Check certificate expiry
kubectl get secret istiod-ca-cert -n istio-system -o jsonpath='{.data.root-cert\.pem}' | base64 -d | openssl x509 -text | grep "Not After"
```

**Permanent fix:** Restart istiod pods to regenerate certificates
```bash
kubectl rollout restart deployment/istiod -n istio-system
kubectl rollout status deployment/istiod -n istio-system
```

### 2. Sidecar Injection Failures on New Nodes

**Symptoms:** New pods scheduled to upgraded nodes missing Istio sidecars

**Diagnosis:**
```bash
# Check if webhook can reach new nodes
kubectl describe mutatingwebhookconfigurations istio-sidecar-injector

# Verify kube-system networking
kubectl get pods -n kube-system -o wide | grep dns
```

**Fix:** Ensure Istio webhook has proper node affinity/tolerations:
```bash
# Check istiod scheduling
kubectl get pods -n istio-system -o wide
kubectl describe deployment istiod -n istio-system | grep -A 10 "Node-Selectors\|Tolerations"
```

### 3. NetworkPolicy Conflicts

**Symptoms:** Service-to-service communication broken after node upgrades

**Diagnosis:**
```bash
# Check Istio NetworkPolicies
kubectl get networkpolicies -A

# Test service connectivity
kubectl exec -it POD_NAME -c istio-proxy -- curl -I http://SERVICE_NAME.NAMESPACE.svc.cluster.local
```

## Workload-Specific Considerations

### StatefulSet Applications
- Use `maxSurge=1, maxUnavailable=0` for database node pools
- Monitor StatefulSet rollout carefully - sidecars must start before app containers
- Check PVC attachment on new nodes

### High-Traffic Services
- Monitor circuit breaker status: `istioctl proxy-config cluster PROXY | grep outlier`
- Watch connection pool metrics during node transitions
- Consider temporary traffic shifting during upgrade

### Ingress/Gateway Workloads
- Verify Gateway configs survive upgrade: `kubectl get gateway -A`
- Check LoadBalancer service endpoints: `kubectl get svc istio-ingressgateway -n istio-system -o wide`
- Monitor ingress controller logs during node transitions

## Pre-Upgrade Checklist

```markdown
Istio + GKE Upgrade Checklist (1.31 → 1.32)

Pre-flight
- [ ] Current Istio version: _____ (check compatibility with K8s 1.32)
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] All webhooks responsive: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations | grep istio`
- [ ] Baseline traffic metrics captured
- [ ] Circuit breaker thresholds documented
- [ ] Gateway/VirtualService configs backed up

Compatibility
- [ ] Istio version supports Kubernetes 1.32
- [ ] No deprecated Istio APIs in use: `istioctl analyze -A`
- [ ] Webhook certificates not expiring soon (check with openssl command above)
- [ ] NetworkPolicy compatibility verified

Upgrade Strategy
- [ ] Istio upgrade completed first (if required)
- [ ] Conservative node pool surge settings: maxSurge=1, maxUnavailable=0
- [ ] Maintenance window during low traffic period
- [ ] Rollback plan documented (including Istio rollback)
- [ ] On-call team includes both K8s and Istio expertise
```

## Post-Upgrade Validation

```bash
# 1. Cluster and Istio health
kubectl get nodes
kubectl get pods -n istio-system
istioctl proxy-status

# 2. Service mesh connectivity
kubectl exec -it POD_NAME -c istio-proxy -- curl -I http://httpbin.NAMESPACE.svc.cluster.local/status/200

# 3. Webhook functionality
kubectl run test-injection --image=nginx --rm -it --restart=Never -n INJECTED_NAMESPACE -- echo "test"
# Should show 2/2 containers (nginx + istio-proxy)

# 4. Traffic flow validation
istioctl proxy-config listeners PROXY_NAME.NAMESPACE
kubectl logs -l app=SAMPLE_APP -c istio-proxy --tail=50

# 5. Certificate and security
istioctl authn tls-check POD_NAME.NAMESPACE SERVICE_NAME.NAMESPACE.svc.cluster.local
```

## Emergency Rollback Plan

If the upgrade causes service mesh issues:

1. **Immediate mitigation** - disable webhook failure policy:
```bash
kubectl patch validatingwebhookconfigurations istiod-default-validator \
  -p '{"webhooks":[{"name":"validation.istio.io","failurePolicy":"Ignore"}]}'
```

2. **Node pool rollback** - create new pool at 1.31, migrate workloads
3. **Istio rollback** - revert to previous Istio version if upgraded
4. **Full cluster rollback** - requires GKE support involvement for control plane

The key to success is **upgrading Istio first** and **monitoring webhooks closely** during the GKE upgrade. Take it slow with conservative surge settings - the mesh adds enough complexity that speed isn't worth the risk.