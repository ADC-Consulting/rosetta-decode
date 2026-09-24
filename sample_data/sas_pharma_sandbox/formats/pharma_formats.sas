/* pharma_formats.sas - PROC FORMAT catalog
   Difficulty: format catalogs must be re-implemented as when/otherwise or
   broadcast lookups in PySpark. */
libname library "./formats";

proc format library=library;
    value agegr1f
        low  -<  18  = '<18'
        18   -<  65  = '18-64'
        65   -<  75  = '65-74'
        75   -  high = '>=75';

    value $sexdec
        'M' = 'Male'
        'F' = 'Female'
        other = 'Unknown';

    value aegrf
        1 = 'Mild'
        2 = 'Moderate'
        3 = 'Severe'
        4 = 'Life-threatening'
        5 = 'Fatal';
run;
