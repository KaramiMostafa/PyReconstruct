# Customized plugin assembly

The customized branch uses a small adapter architecture because upstream
PyReconstruct does not currently expose a general plugin entry-point API.

```text
SynapseWeb/PyReconstruct (upstream application)
                  │
                  ▼
KaramiMostafa/PyReconstruct:cellpose-custom-model
thin host UI, dialogs, viewer integration, and menu assembly
                  │ one public API boundary
                  ▼
PyReconstruct_connector_tracking_plugin
authoritative registry plus PyReconstruct ↔ algorithm/data adapters
          │                         │
          ▼                         ▼
Hungarian tracking core       Bayesian Transformer core
independent ROI-table library independent ROI-table library
```

The host never imports either tracking engine. It obtains the menu from
`pyrecon_connector.get_plugin_menu_spec()` and invokes only public connector
functions. The connector converts PyReconstruct sections and traces into the
inputs required by each engine, runs the operation, and writes validated
results back to the open series.

## Registered capabilities

| Capability | Implementation | External engine |
|---|---|---|
| Hungarian DAPI tracking | Connector adapter | `tracking_hungarian` repository |
| Bayesian DAPI tracking | Connector adapter | `tracking_BayesianTransformer` repository |
| U-Net segmentation | Connector-native adapter | PyTorch |
| Cellpose-SAM segmentation | Connector-native adapter | Cellpose/PyTorch |
| DAPI-guided mRNA mapping | Connector-native adapter | None |
| Expert feedback | Connector persistence plus host review UI | None |
| Validation/intensity analysis | Connector-native adapter | NumPy/Matplotlib |
| Channels and ROI overlays | Thin customized-host viewer integration | None |

The machine-readable source of truth is
`pyrecon_connector/plugin_registry.py` in the connector repository. A missing
connector leaves PyReconstruct usable and replaces the Plug-In menu with setup
instructions.

## Development rules

- Keep general PyReconstruct behavior synchronized with upstream.
- Put PyReconstruct data conversion and write-back logic in the connector.
- Keep reusable algorithms independent of PyReconstruct objects and GUI code.
- Add every new plugin to the connector registry and its assembly tests.
- Use Conventional Commit subjects on `cellpose-custom-model`.
- Run both repositories' tests before pushing a synchronized change.

Validate the installed assembly with:

```bash
python -c "from pyrecon_connector import audit_plugin_assembly; import pprint; pprint.pp(audit_plugin_assembly())"
```
