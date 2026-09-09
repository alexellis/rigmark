# First-party serving records

These are the public-safe metadata inputs used for Alex Ellis's appliances.
They describe the server state presented to RigMark; they are not benchmark
results, performance claims, or generic templates for superficially similar
hardware.

Each record is an operator-declared snapshot. Its capture date and immutable
recipe, model, engine, and image revisions make later results interpretable.
RigMark fingerprints the record inside its JSON receipt, but cannot attest that
the declared software or hardware was actually running.

| Appliance | Record | Captured |
|---|---|---|
| Qwen 3.8 27B FP8 on one RTX PRO 6000 | [`alexellis-qwen38-27b-fp8-rtxpro6000.json`](alexellis-qwen38-27b-fp8-rtxpro6000.json) | 9 September 2026 |
| DeepSeek V4 Flash 0731 NVFP4 on two DGX Sparks | [`alexellis-ds4f-0731-nvfp4-2x-dgx-spark.json`](alexellis-ds4f-0731-nvfp4-2x-dgx-spark.json) | 9 September 2026 |
| GLM-5.3-Flash NVFP4 on two DGX Sparks | [`alexellis-glm53-flash-nvfp4-2x-dgx-spark.json`](alexellis-glm53-flash-nvfp4-2x-dgx-spark.json) | 9 September 2026 |

Copy the relevant file to the ignored local input before running a comparable
appliance:

```bash
cp examples/serving-records/alexellis-ds4f-0731-nvfp4-2x-dgx-spark.json metadata.json
```

Then edit every field that differs. In particular, do not retain an image
digest, model revision, drafter, context limit, scheduler, or traffic
declaration merely because the hardware model is the same.

