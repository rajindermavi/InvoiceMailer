
# 1. Client List

**Single xlsx File**

## Expected Columns

| Column            | Required  |
|-------------------|-----------|
| Head Office       | Yes       |
| Customer Number   | Yes       |
| emailforinvoice1  | Yes       |
| emailforinvoice2  | Yes       |
| emailforinvoice3  | Yes       |
| emailforinvoice4  | Yes       |
| emailforinvoice5  | Yes       |

# 2. SOA Files

**PDFs, 1 per Head Office**

## File pattern

Statement of Account for-<HEAD_OFFICE_NAME>.PDF

# 3. Invoices

**PDFs, many files**

## File pattern

<CUSTOMER_NUMBER> Invoice <INVOICE_NO> <SHIP_NAME>.PDF

Invoice date must be listed.