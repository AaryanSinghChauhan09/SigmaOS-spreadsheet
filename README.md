    # SigmaOS-spreadsheet

    CSV spreadsheet engine with formulas

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - native

    ## Design principles applied
    - **Defensive Programming**
- **Fail-Fast**
- **Least Astonishment**
- **KISS**
- **Separation of Concerns**
- **Deterministic Testing**

    ## Usage
    Verbs: `load, set, eval, dump, sum`

    ```
    $ sigma-sheet set A1 10
$ sigma-sheet set A2 32
$ sigma-sheet set B1 "=A1 + A2"
$ sigma-sheet eval B1
42
$ sigma-sheet sum A1:A2
42
$ sigma-sheet dump --out sheet.csv

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
