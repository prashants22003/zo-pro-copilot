# Schema — Application allow-list

Geography and people. Both domain agents get the tables below (read). Display prefix: `Application.*`.

No clock cutoff on these dimensions for MVP (current rows only).

## Look here first

| Question about… | Path |
|---|---|
| Region, state, country of a **customer** | `sales.customers.delivery_city_id` → `cities` → `state_provinces` → `countries` |
| Region of a **supplier** | `purchasing.suppliers.delivery_city_id` → same chain |
| Salesperson or PO contact name | `application.people.person_id` |
| Delivery method name | `application.delivery_methods` |
| Stock transaction type name | `application.transaction_types` |

## `application.cities` (Application.Cities)

`city_id`, `city_name`, `state_province_id`

WWI also has geo columns; skip `geography` types in Postgres.

## `application.state_provinces` (Application.StateProvinces)

`state_province_id`, `state_province_code`, `state_province_name`, `country_id`, `sales_territory` (use if present — handy for “region”)

## `application.countries` (Application.Countries)

`country_id`, `country_name`, `iso_alpha3_code`, `region`, `subregion`

For “which region has more growth”, prefer:

1. `state_provinces.sales_territory` if populated
2. Else `countries.region` / country name
3. Else city name only if the user asked for city

Always **cite** which grain you used.

## `application.people` (Application.People)

`person_id`, `full_name`, `is_sales_person`, `is_employee` (and similar flags if migrated)

Join:

- `sales.orders.salesperson_person_id`
- `purchasing.purchase_orders.contact_person_id`
- supplier/customer contact person ids

Do not pull `hashed_password`, `logon_name`, or photo.

## `application.delivery_methods` (Application.DeliveryMethods)

`delivery_method_id`, `delivery_method_name`

## `application.payment_methods` (Application.PaymentMethods)

`payment_method_id`, `payment_method_name`

## `application.transaction_types` (Application.TransactionTypes)

`transaction_type_id`, `transaction_type_name` — decode warehouse and AR/AP transactions.

## Do not

- Grant `website` or system parameters that leak connection strings
- Treat people as customers (customers live in `sales.customers`)
