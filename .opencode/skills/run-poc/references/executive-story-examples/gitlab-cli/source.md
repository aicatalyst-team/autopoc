Ledger Scan is a fictional command line tool intended to find inconsistent records in local ledger files.
Assess local scanning and large-file handling without a web interface.
The synthetic record used a local command line process and two fixture files without deploying a service.
Large-file completion and integration with other tools were not tested.
Complete the large-file check and retain its exit status before recommending batch use.
Scan a consistent ledger
Check the exit status for a consistent fixture file.
The consistent fixture completed with the expected exit status.
Scan a large ledger with duplicate references
Check duplicate reporting across a large fixture file.
The large-file attempt stopped before producing a final result.
One check passed and one remained incomplete.
