# Context and Operating Evidence

**No Production Access**
There is no production alert feed available. The local OpenTelemetry Demo estate is the entire evidence base. All metrics, throughput claims, and sizing numbers represent the engine's performance under injected faults in this synthetic environment.

**Build vs Buy**
This pattern is implemented commercially by ServiceNow ITOM, BigPanda, Moogsoft, and Dynatrace Davis. This project demonstrates a custom, cross-tool correlation engine using open-source primitives.

**Resource Constraints & Limitations**
Due to memory constraints and service breakage, the following adjustments define the estate's boundaries:
- **Removed Services**: 
  - `product-catalog`: Removed due to unresolvable crash-loops (cause unknown, distroless image makes it undiagnosable).
  - `cadvisor`: Removed for memory overhead and port conflicts.
  - `toxiproxy`: Removed for memory overhead.
- **Excluded Services**: Because `product-catalog` is missing, the `checkout` service permanently returns 500s. It is completely excluded from all measurements and rules.
- **Missing Metrics**: There are no service-level latency metrics available on `cart`, so the `HighLatency` rule was cut.
- **Blackbox Probing Gap**: Blackbox does not detect partial degradation. The frontend will happily return a 200 OK even if the backend `cart` service is completely broken.

**Measurement Characteristics**
- **Detection Lag**: There is a ~2 minute detection lag built into the estate due to `metric_expiration: 60s` in the OpenTelemetry collector plus `for: 1m` in Prometheus rules.
- **Scope**: Exactly 4 fault types are measured against one single topology, using one labeller.
- **Baseline Unresolved Components**: The estate currently has **35% unresolved component identifiers** at baseline. This is the official starting point that Phase 4's resolver must improve upon to hit the `<5%` target.
