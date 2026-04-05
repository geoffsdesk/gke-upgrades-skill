# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful sequencing to avoid breaking traffic flow. Here's your battle-tested approach:

## Pre-Upgrade: Istio Compatibility Check

**Critical first step:** Verify your Istio version supports Kubernetes 1.32:

```bash
# Check current Istio version
istioctl version

# Check Istio support matrix
# https://istio.io/latest/docs/releases/supported-releases/
```

**Istio version requirements for K8s 1.32:**
- Istio 1.20+ officially supports Kubernetes 1.32
- Istio 1.19 may work but test thoroughly
- Istio 1.18 and below: **upgrade Istio first**

## Upgrade Sequence (Critical Order)

### Phase 1: Control Plane Upgrade
```bash
# Apply "no minor or node upgrades" exclusion to prevent auto-upgrades during validation
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "istio-upgrade-freeze" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

### Phase 2: Validate Istio Control Plane Health
```bash
# Check istiod health after CP upgrade
kubectl get pods -n istio-system
istioctl proxy-status

# Validate admission webhooks are working
kubectl run istio-test --image=nginx --labels="app=test" --dry-run=client -o yaml | kubectl apply -f -
kubectl get pod istio-test -o yaml | grep sidecar

# Clean up test
kubectl delete pod istio-test
```

### Phase 3: Node Pool Upgrades (if validation passes)
```bash
# Use conservative surge settings for mesh workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools sequentially, not parallel
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

## Service Mesh-Specific Risks & Mitigations

### 1. Admission Webhook Failures (Primary Risk)

**Symptom:** Pods fail to create with "admission webhook rejected" after CP upgrade

**Prevention:**
```bash
# Before upgrading, check webhook configurations
kubectl get mutatingwebhookconfigurations | grep istio
kubectl describe mutatingwebhookconfigurations istio-sidecar-injector
```

**Emergency fix if webhooks break:**
```bash
# Temporarily disable sidecar injection
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'

# Or disable entirely (pods will deploy without sidecars)
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","namespaceSelector":{"matchLabels":{"istio-injection":"disabled"}}}]}'
```

### 2. Envoy Proxy Compatibility

**Risk:** Envoy sidecar version incompatible with new Kubernetes API changes

**Validation:**
```bash
# After CP upgrade, check proxy versions and status
istioctl proxy-status
istioctl proxy-config cluster -o json | jq '.[].name' | sort | uniq

# Look for version mismatches or error states
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="istio-proxy")].image}{"\n"}{end}' | grep istio-proxy
```

### 3. Certificate/TLS Issues

**Risk:** Istio's certificate management may fail with API changes

**Monitor:**
```bash
# Check certificate validity
kubectl get secret -n istio-system | grep cacerts
istioctl authn tls-check POD_NAME.NAMESPACE.svc.cluster.local

# Validate mTLS is working
istioctl authn tls-check WORKLOAD_NAME.NAMESPACE
```

### 4. Gateway and VirtualService Compatibility

**Risk:** API version changes may affect Istio CRDs

**Check:**
```bash
# Verify gateway and routing still works
kubectl get gateway,virtualservice,destinationrule -A
istioctl analyze -A

# Test ingress traffic
curl -v http://YOUR_GATEWAY_URL/health
```

## Detailed Validation Checklist

After each phase:

```bash
# Control plane health
kubectl get pods -n istio-system
kubectl get svc -n istio-system

# Proxy health
istioctl proxy-status | grep -v SYNCED

# Configuration distribution
istioctl proxy-config cluster PILOT_POD.istio-system | head -20

# Sidecar injection working
kubectl get pods -A -o wide | grep -E "2/2|3/3" | head -5

# Ingress traffic flow
curl -v http://YOUR_INGRESS_ENDPOINT/

# Inter-service mTLS
istioctl authn tls-check SERVICE_A.NAMESPACE SERVICE_B.NAMESPACE
```

## Rollback Strategy (If Things Break)

### If Control Plane Breaks Istio:
```bash
# Option 1: Patch webhooks to non-blocking
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'

# Option 2: Disable injection temporarily
kubectl label namespace NAMESPACE istio-injection-

# Option 3: Reinstall Istio control plane
istioctl install --set values.istiodRemote.enabled=false --set values.pilot.env.EXTERNAL_ISTIOD=false
```

### If Node Upgrades Break Workloads:
```bash
# Create new node pool at previous version
gcloud container node-pools create emergency-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 3

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL

# Let scheduler migrate workloads naturally
```

## Post-Upgrade Monitoring (First 24 Hours)

Focus on these service mesh metrics:

```bash
# Error rates by service
kubectl top pods -A --containers | grep istio-proxy

# Check for 5xx errors in Envoy
kubectl logs -n NAMESPACE POD_NAME -c istio-proxy | grep "HTTP/1.1\" 5"

# Certificate expiry monitoring
istioctl proxy-config secret POD_NAME.NAMESPACE | grep -E "EXPIRED|default"

# Configuration sync issues
istioctl proxy-status | grep -E "STALE|NOT SENT"
```

**Key insight:** The control plane upgrade is the highest risk phase for service mesh. Node pool upgrades usually go smoothly if the CP upgrade succeeded. Always validate mesh functionality thoroughly before proceeding to node upgrades.

**When to call for help:** If admission webhooks fail completely and the failurePolicy patches don't work, or if `istioctl proxy-status` shows widespread STALE configurations after CP upgrade, engage Istio community support or your service mesh vendor immediately.

Remove the maintenance exclusion once you've validated everything works:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "istio-upgrade-freeze"
```