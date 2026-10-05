# Sample data (synthetic)

Made-up data for trying the app. It is not based on any real company, client or person.

There are two sets. Upload the RACM in step 1 and its matching transcript in step 3.

**Set 1: a control that is designed well (expected result: Adequate, no gaps)**

| File | Use it for |
|---|---|
| `sample_racm.xlsx` | Step 1: upload under "Upload RACM file from your computer". |
| `sample_walkthrough_transcript.txt` | Step 3: "Upload transcript". |
| `sample_walkthrough_transcript.docx` | Step 3: the same transcript as a Word file (use either one). |

Control: weekly supplier payment approval. The payment run is prepared by one person and approved by
two others, and all six attributes are documented.

**Set 2: a control with a design problem (expected result: Inadequate, with one gap)**

| File | Use it for |
|---|---|
| `sample_inadequate_racm.xlsx` | Step 1. |
| `sample_inadequate_walkthrough_transcript.txt` | Step 3. |
| `sample_inadequate_walkthrough_transcript.docx` | Step 3: the same transcript as a Word file. |

Control: manual journal entry approval. The objective requires approval by someone independent of the
preparer, but in the walkthrough the interviewee says they prepare **and** approve the journals
themselves. All six attributes are documented, so the design assessment can reach a firm conclusion:
**Inadequate**, with one drafted gap ("Lack of independence between control roles", root cause
"Segregation of duties"). In the Excel export that shows as Applicable = No, with the reason and the
Gap block filled in.

Today the app detects one kind of design gap, an independence (segregation of duties) conflict, so a
control produces at most one gap.

## The standard RACM headers

The same headers the app uses in its Excel export, so an exported RACM can be uploaded again:

Engagement ID, Client, OpCo, Area, Mega Process, Process, Sub-process, Control ID, Control Reference,
Control Title, Risk ID, Risk Description, Control Objective, Suggested Control Description,
Control Frequency, Control Nature, Control Type, Expected Evidence,
Suggested Test Procedures (ToD), Suggested Test Procedures (ToE)

Only **Risk ID** and **Control ID** (or **Control Reference**) are required. Older names such as
`Risk Ref`, `Control Ref`, `Process Name`, `Suggested Control`, `Control Evidence` and
`Frequency of Control` are still accepted. The sheet should be named `RACM Upload`
(otherwise the first visible sheet is used), and only the first control row is read.
