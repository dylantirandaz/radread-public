# Source, access, and attribution notice

This public package redistributes **no radiograph pixels, case-gold labels, reference
boxes, oracle answers, or source annotation files**. Task/provenance metadata does not
convey a license to access, upload, or redistribute the underlying datasets. Each
recipient must obtain source files legitimately and follow the current provider terms.
Historical mirror/archive names in `envs/radread-public/environment/sources.jsonl`
record provenance only; they are not recommendations to bypass access controls.
No blanket license is newly assigned to
third-party data or code by this release. Existing rights and attributions remain with
their respective holders.

The `public150-pass5-audit1` correction comprises the same 150 studies as
`public150-pass5`: 14 NIH, 112 ChestX-Det, 10 VinDr, 3 RSNA, 7 GRAZ and 4 FracAtlas.
The correction regrades the same saved responses after two source-backed reference
changes and a laterality-audit fix; it collects no new responses or clinical labels.
`scripts/prepare_images.py` adapts the source transforms used by RadRead's historical
image helper for the original five sources and adds local FracAtlas JPEG preparation,
omitting network fetches and unrelated sources.
`envs/radread-public/verifier/read_scoring.py` is the original deterministic grader,
copied unchanged, without its case-gold data. The sandbox, verifiers adapter, evaluation
launcher and aggregation code are public; dependencies retain their own licenses.
The project does not grant additional rights to upstream software merely by including
or adapting it.

Upstream annotations support findings/localization to the extent described by each
provider; they do not establish clinical validation of RadRead's benchmark-authored
diagnosis strings or management categories. Known template leakage, lexical diagnosis
grading and `urgent_review` acceptance on 148/150 keys remain unresolved. This is an
outcome-selected challenge cohort, not an independent clinical holdout; its source
subsets are too small for robust per-source comparisons.

## NIH ChestX-ray14 (14 studies; also upstream of ChestX-Det and RSNA)

Provider: NIH Clinical Center. Official source/download and documentation:

- [NIH Clinical Center ChestX-ray dataset](https://nihcc.app.box.com/v/ChestXray-NIHCC)
- [Provider FAQ](https://nihcc.app.box.com/v/ChestXray-NIHCC/file/249502714403)
- Wang et al., *ChestX-ray8: Hospital-scale Chest X-ray Database and Benchmarks on
  Weakly-Supervised Classification and Localization of Common Thorax Diseases*, CVPR
  2017. [Paper](https://openaccess.thecvf.com/content_cvpr_2017/html/Wang_ChestX-Ray8_Hospital-Scale_Chest_CVPR_2017_paper.html)

The provider FAQ describes usage as unrestricted while requesting the original download
link, NIH Clinical Center acknowledgment, and citation of Wang et al. Retain these
attributions; do not reinterpret this package as a new license grant. The provider
supplies PNGs, not DICOMs. Preparation preserves original grayscale 1024×1024 PNG bytes,
or converts to grayscale and LANCZOS-resizes if necessary.

## ChestX-Det (112 studies)

Provider: Deepwise AI Lab; derived from NIH ChestX-ray14.

- [Official ChestX-Det repository and download instructions](https://github.com/Deepwise-AILab/ChestX-Det-Dataset)
- [Repository LICENSE](https://github.com/Deepwise-AILab/ChestX-Det-Dataset/blob/main/LICENSE)

The official repository has an Apache-2.0 LICENSE and separately links image ZIPs hosted
by Deepwise. The licensing scope over those external archives is not explicit enough
here to assert blanket pixel-redistribution rights. Consult the provider's current
instructions and applicable terms before acquisition/use. This package ships neither
those archives nor their annotation files. Keep Deepwise and original NIH attribution;
cite the dataset publications requested by the official repository. Preparation follows
the NIH PNG path above. Nothing in this notice relabels the external images as either
unconditionally Apache-licensed or universally research-only.

## VinDr-CXR (10 studies)

Providers: Vingroup Big Data Institute and participating hospitals, distributed through
PhysioNet.

- [VinDr-CXR 1.0.0](https://physionet.org/content/vindr-cxr/1.0.0/)
- [Dataset-linked license](https://physionet.org/content/vindr-cxr/view-license/1.0.0/)
- [Dataset-linked data use agreement](https://physionet.org/content/vindr-cxr/view-dua/1.0.0/)
- Nguyen et al., *VinDr-CXR: An open dataset of chest X-rays with radiologist's
  annotations*, Scientific Data (2022). [DOI](https://doi.org/10.1038/s41597-022-01498-w)

PhysioNet requires credentialed access, the specified CITI training, and a signed DUA.
The dataset-linked current license/DUA text governs; the 1.0.0 URLs above identify the
dataset release, not a claim that the terms document has that version number. Do not
share restricted-data access, use an ungated mirror to bypass these requirements, or
redistribute locally prepared images through this repository.

The official files are DICOM. The historical benchmark used processed 8-bit grayscale
PNGs whose DICOM conversion is insufficiently documented. No verified official
pixel-equivalent PNG release is identified here. `scripts/prepare_images.py` only performs the
known LANCZOS resize on legitimately held equivalent `L`-mode PNGs. Reproducing exact
published VinDr pixels requires additional authorized preprocessing provenance or
equivalent legitimate inputs; arbitrary DICOM rendering is not an exact reproduction.

Before sending any restricted data to a model provider, follow the DUA and PhysioNet's
[responsible LLM-use guidance](https://physionet.org/news/post/llm-responsible-use/) and
[FAQs](https://physionet.org/about/faqs/). Prefer local inference. Ordinary cloud API
availability or default settings do not establish permission: applicable zero-retention,
no-training, no-human-review, and access conditions must actually be satisfied.

## RSNA Pneumonia Detection Challenge (3 studies)

Providers: RSNA, Society of Thoracic Radiology, and NIH Clinical Center.

- [Official challenge page, download alternatives, and linked Terms of Use](https://www.rsna.org/artificial-intelligence/ai-image-challenge/rsna-pneumonia-detection-challenge-2018)
- [Kaggle challenge entry point](https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge)
- Shih et al., *Augmenting the National Institutes of Health Chest Radiograph Dataset
  with Expert Annotations of Possible Pneumonia*, Radiology: Artificial Intelligence
  1(1), 2019. [DOI](https://doi.org/10.1148/ryai.2019180041)
- Also cite Wang et al., CVPR 2017, and acknowledge NIH Clinical Center (above).

The current RSNA-hosted terms linked from the official page permit commercial and
noncommercial uses with attribution requirements and prohibit re-identification. Do not
assume that a historical description of noncommercial-only use is the current universal
rule. Follow the actual terms for your acquisition channel, including any Kaggle access
and acceptance requirements; do not substitute a mirror for required acceptance.
This package takes authorized local DICOMs and redistributes no pixels. Include NIH/RSNA
links and the requested citations with downstream use where required.

Historical rendering decoded the embedded JPEG-baseline grayscale frame directly.
The preparer retains that path and can additionally use uncompressed uint8 pixels
without windowing/rescaling. Those encodings are not guaranteed pixel-equivalent;
exact comparison with published scores requires matching the historical rendering.

## GRAZPEDWRI-DX (7 studies)

Provider: Medical University of Graz / dataset authors.

- [GRAZPEDWRI-DX figshare record](https://figshare.com/articles/dataset/GRAZPEDWRI-DX/14825193)
- [Versioned dataset DOI](https://doi.org/10.6084/m9.figshare.14825193.v2)
- [Official record metadata](https://api.figshare.com/v2/articles/14825193)
- Nagy et al., *A pediatric wrist trauma X-ray dataset (GRAZPEDWRI-DX) for machine
  learning*, Scientific Data (2022). [Paper](https://www.nature.com/articles/s41597-022-01328-z)

The cited figshare release is CC BY 4.0. Retain creator, dataset, DOI, license, and change
attribution; do not attempt re-identification. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Original images are 16-bit PNGs in `images_part1.zip` through `images_part4.zip`.
Local preparation keeps the top byte for non-`L` images and resizes with LANCZOS to
1024×1024. These are modifications to source pixels, not a new original image license.

## FracAtlas (4 studies)

Creators: Iftekharul Abedeen, Md. Ashiqur Rahman, Fatema Zohra Prottyasha, Tasnim Ahmed,
Tareque Mohmud Chowdhury, and Swakkhar Shatabda.

- [Official FracAtlas figshare record and downloads](https://figshare.com/articles/dataset/The_dataset/22363012)
- [Dataset DOI](https://doi.org/10.6084/m9.figshare.22363012)
- [Official record metadata, including the dataset license](https://api.figshare.com/v2/articles/22363012)
- Abedeen et al., *FracAtlas: A Dataset for Fracture Classification, Localization and
  Segmentation of Musculoskeletal Radiographs*, Scientific Data 10, 521 (2023).
  [Paper](https://www.nature.com/articles/s41597-023-02432-4)
- [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/)

The figshare record and the paper's Usage Notes explicitly license the dataset under
CC BY 4.0, permitting commercial use and adaptation with attribution. Retain the creators,
dataset and paper citations, source and license links, and an indication of changes.
This dataset license is distinct from the authors' code repository license.

The paper's Data collection and cleanup and Folder structure sections document that
the released originals are JPEGs, named `IMG` plus seven zero-padded digits and `.jpg`,
inside `FracAtlas/images/Fractured/` or `FracAtlas/images/Non_fractured/` in
`FracAtlas.zip`. The source hospitals' proprietary software performed the DICOM-to-JPEG
conversion; this package does not guess or reproduce that conversion from DICOM.
Use legitimately acquired released JPEGs under `<input-root>/fracatlas/`, retaining
their original filenames. The preparer searches this directory recursively and maps
`IMG<seven digits>.jpg` to `images/frac_IMG<seven digits>.png`.

RadRead preparation decodes the released JPEG with Pillow, converts to 8-bit grayscale
(`L`), and, when needed, resizes directly to 1024×1024 with LANCZOS before saving PNG.
There is no crop, padding, automatic orientation, contrast normalization, windowing,
or annotation overlay. These are benchmark transformations, not an assertion that
FracAtlas distributes 1024×1024 grayscale PNGs. Exact equivalence to previously
prepared commercial images requires checking the source release and rendering
provenance; the historical FracAtlas helper is not available in this public package.
The provider has revised the dataset since the paper, so retain the actual acquired
version and file checksums rather than assuming that the current release is identical.
Alternatively, legitimately held already-prepared `L`-mode 1024×1024 PNGs named
`frac_IMG<seven digits>.png` or `IMG<seven digits>.png` can be supplied under the same
input directory. They are copied byte-for-byte, not re-rendered. Other PNG modes or
sizes are rejected because this path preserves prepared pixels rather than guessing
their preprocessing. Supply only one matching JPEG or PNG per study: ambiguous inputs
are rejected, as are existing outputs unless `--overwrite` is explicitly requested.
Preserving a prepared PNG does not establish its upstream release or transformation
history; retain its provenance and checksum separately.
This package redistributes neither the JPEGs nor their annotations or transformed PNGs.

## Previously unpublished study identifiers and provenance gaps

The prior website/results release left eight `com_` tasks staged locally rather than
published to the separate public benchmark repository. All eight original identifiers
are now represented in the 150-row `envs/radread-public/environment/sources.jsonl`:

| Source | Original filename |
|---|---|
| FracAtlas | `IMG0002344.jpg` |
| FracAtlas | `IMG0002572.jpg` |
| FracAtlas | `IMG0001869.jpg` |
| FracAtlas | `IMG0002414.jpg` |
| GRAZPEDWRI-DX | `1073_0736320189_02_WRI-L2_F008.png` |
| GRAZPEDWRI-DX | `1071_0690023332_04_WRI-L1_F007.png` |
| GRAZPEDWRI-DX | `1457_0461840394_01_WRI-R2_F008.png` |
| NIH ChestX-ray14 | `00010125_004.png` |

Each corresponding source row records the inherited prepared-PNG SHA256. The NIH row
also records `BBox_List_2017.csv` and historical HF mirror revision
`36778e3b0e4f4b4fad31d1728d6190f3eda5b543`; this is provenance, not an access
recommendation or an original NIH archive-version guarantee. The original FracAtlas
archive version is explicitly unrecorded, and these GRAZ rows do not record an exact
acquired image-archive revision. Dataset links and cited versions above must not be
substituted for missing acquisition records.

Prepared-file hashes identify inherited bytes; they do not prove an upstream archive
revision or the equivalence of a fresh render. FracAtlas JPEG preparation is supported,
but matching those inherited PNG bytes from current originals has not been established.
VinDr's historical DICOM conversion is insufficiently documented, and RSNA's supported
encodings are not guaranteed equivalent. No blanket byte-for-byte reproduction claim
is made, and no missing archive revision is inferred.

## Release boundary

Prompts/checklists, identifiers, metadata provenance, schemas/instructions, sandbox
build code, the installable evaluation adapter, verifier, and submission/evaluation
scripts are supplied. No upstream data license is superseded, expanded, or transferred.
No source access is automatically accepted on the user's behalf.

Public code is not the same as agent access. Build the agent image from
`envs/radread-public/environment/` only. Gold and the verifier belong on the grading
host or in a separate, post-agent verifier step; they must not be present in the
evaluated agent's filesystem. The API adapter sends only task prompts and images
to the model provider and omits image payloads from saved transcripts.

Case gold, oracle answers, commercial environments, private repository history,
credentials, and answer-bearing audit/baseline reports are not part of this release.
The scored API adapter and aggregation scripts
require an independently authorized key; this release provides no public key or hosted
grading service. Manual inference and submission collection do not require one.
Public traces already contain passing model answers: withholding a separate gold file
does not make this cohort a secret or contamination-free holdout.

Reference-bearing scoring reports and locally generated images must stay outside public
uploads even when an individual source permits broader redistribution. Source terms and
links may change; consult the provider at acquisition time.
