SET DEFINE OFF;

INSERT INTO MANUFACTURER
SELECT 920000+n,
       'Manufacturer '||n,
       'LIC-920'||TO_CHAR(n,'FM000'),
       '900000'||TO_CHAR(n,'FM0000'),
       'manufacturer'||n||'@example.com',
       'Research Park, Block '||n,
       'India',
       'CDSCO'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO DRIVER
SELECT 920000+n,
       'Driver '||n,
       'DL-920'||TO_CHAR(n,'FM000'),
       '910000'||TO_CHAR(n,'FM0000'),
       DATE '2028-12-31',
       'Cold Chain Certified',
       'Active'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO VEHICLE
SELECT 920000+n,
       'TN-09-CT-'||TO_CHAR(920000+n),
       CASE MOD(n,3) WHEN 0 THEN 'Freezer Van' WHEN 1 THEN 'Refrigerated Van' ELSE 'Cold Chain Truck' END,
       CASE MOD(n,3) WHEN 0 THEN 'Deep Freeze' ELSE 'Active Refrigeration' END,
       CASE MOD(n,3) WHEN 0 THEN -25 ELSE 2 END,
       CASE MOD(n,3) WHEN 0 THEN -15 ELSE 8 END,
       1000+n*100,
       'Available',
       DATE '2026-08-01'+n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO WAREHOUSE
SELECT 920000+n,
       'Cold Storage Warehouse '||n,
       'Industrial Estate, Block '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Chennai' WHEN 1 THEN 'Bengaluru' ELSE 'Hyderabad' END,
       CASE MOD(n,3) WHEN 0 THEN 'Tamil Nadu' WHEN 1 THEN 'Karnataka' ELSE 'Telangana' END,
       3000+n*100,
       'Regional',
       'Certified',
       'Warehouse Manager '||n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO DISTRIBUTION_CENTER
SELECT 920000+n,
       'Distribution Centre '||n,
       'Logistics Park, Block '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Chennai' WHEN 1 THEN 'Bengaluru' ELSE 'Hyderabad' END,
       CASE MOD(n,3) WHEN 0 THEN 'Tamil Nadu' WHEN 1 THEN 'Karnataka' ELSE 'Telangana' END,
       1500+n*50,
       '920000'||TO_CHAR(n,'FM000'),
       'Centre Manager '||n,
       'Certified'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO HEALTHCARE_FACILITY
SELECT 920000+n,
       'Healthcare Facility '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Hospital' WHEN 1 THEN 'Medical Centre' ELSE 'Clinic' END,
       'HCF-920'||TO_CHAR(n,'FM000'),
       'Health Avenue, Building '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Chennai' WHEN 1 THEN 'Bengaluru' ELSE 'Hyderabad' END,
       CASE MOD(n,3) WHEN 0 THEN 'Tamil Nadu' WHEN 1 THEN 'Karnataka' ELSE 'Telangana' END,
       '930000'||TO_CHAR(n,'FM0000'),
       'Refrigerated Storage',
       'Active'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO ROUTE
SELECT 920000+n,
       'Warehouse '||n,
       'Healthcare Facility '||n,
       20+n*2.5,
       45+n*5,
       'Road',
       'Active'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO PHARMACEUTICAL_PRODUCT
SELECT 920000+n,
       920000+n,
       CASE MOD(n,3) WHEN 0 THEN 'Insulin Injection '||n WHEN 1 THEN 'Hepatitis Vaccine '||n ELSE 'COVID Vaccine '||n END,
       CASE MOD(n,3) WHEN 0 THEN 'Human Insulin' WHEN 1 THEN 'Hepatitis B Antigen' ELSE 'Viral Antigen Vaccine' END,
       'Injection',
       CASE MOD(n,3) WHEN 0 THEN '100 IU/ml' WHEN 1 THEN '20 mcg/ml' ELSE '0.5 ml' END,
       CASE MOD(n,3) WHEN 0 THEN 'Biologic' ELSE 'Vaccine' END,
       CASE MOD(n,3) WHEN 0 THEN 'Refrigerated' WHEN 1 THEN 'Refrigerated' ELSE 'Frozen' END,
       365+n*30,
       'Approved'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO STORAGE_CONDITION
SELECT 920000+n,
       920000+n,
       CASE MOD(n,3) WHEN 2 THEN -25 ELSE 2 END,
       CASE MOD(n,3) WHEN 2 THEN -15 ELSE 8 END,
       30,
       60,
       'Medium',
       'Maintain recommended pharmaceutical storage conditions'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO PRODUCT_BATCH
SELECT 920000+n,
       920000+n,
       'BATCH-920'||TO_CHAR(n,'FM000'),
       DATE '2026-01-01'+n,
       DATE '2027-12-31'+n,
       1000+n*100,
       'Available',
       CASE MOD(n,4) WHEN 0 THEN 'Pending' ELSE 'Passed' END
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO QUALITY_TEST
SELECT 920000+n,
       920000+n,
       DATE '2026-02-01'+n,
       CASE MOD(n,3) WHEN 0 THEN 'Stability Test' WHEN 1 THEN 'Purity Test' ELSE 'Temperature Test' END,
       CASE MOD(n,4) WHEN 0 THEN 'Pending' ELSE 'Passed' END,
       'Quality Analyst '||n,
       'Quality inspection record '||n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO STORAGE_UNIT
SELECT 920000+n,
       920000+n,
       'Storage Unit '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Freezer' ELSE 'Refrigerator' END,
       CASE MOD(n,3) WHEN 0 THEN -25 ELSE 2 END,
       CASE MOD(n,3) WHEN 0 THEN -15 ELSE 8 END,
       500+n*50,
       'Operational',
       DATE '2025-01-01'+n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO INVENTORY
SELECT 920000+n,
       920000+n,
       920000+n,
       500+n*20,
       50+n*5,
       SYSDATE,
       'Available'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO INVENTORY_TRANSACTION
SELECT 920000+n,
       920000+n,
       CASE MOD(n,3) WHEN 0 THEN 'STOCK_IN' WHEN 1 THEN 'STOCK_OUT' ELSE 'RESERVATION' END,
       50+n*10,
       SYSDATE-n,
       'SAMPLE',
       920000+n,
       'Inventory Operator '||n,
       'Inventory transaction record '||n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO ROUTE_STOP
SELECT 920000+n,
       920000+n,
       'Route Stop '||n,
       'Distribution Centre',
       1,
       TIMESTAMP '2026-11-04 08:00:00'+NUMTODSINTERVAL(n,'HOUR'),
       TIMESTAMP '2026-11-04 08:30:00'+NUMTODSINTERVAL(n,'HOUR'),
       NULL,
       NULL
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO IOT_SENSOR
SELECT 920000+n,
       920000+n,
       'Temperature',
       'SENSOR-920'||TO_CHAR(n,'FM000'),
       'CryoSense',
       DATE '2026-01-01'+n,
       DATE '2026-09-01',
       DATE '2027-09-01',
       'Active',
       0.30
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO SHIPMENT
SELECT 920000+n,
       DATE '2026-11-01'+n,
       DATE '2026-11-05'+n,
       NULL,
       'WAREHOUSE',
       920000+n,
       'HEALTHCARE_FACILITY',
       920000+n,
       CASE MOD(n,3) WHEN 0 THEN 'In Transit' WHEN 1 THEN 'Dispatched' ELSE 'Pending' END,
       CASE MOD(n,2) WHEN 0 THEN 'High' ELSE 'Medium' END,
       100+n*10,
       920000+n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO SHIPMENT_ITEM
SELECT 920000+n,
       920000+n,
       100+n*10,
       'Insulated Carton',
       'Maintain specified product temperature'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO VEHICLE_ASSIGNMENT
SELECT 920000+n,
       920000+n,
       920000+n,
       920000+n,
       DATE '2026-11-01'+n,
       TIMESTAMP '2026-11-04 08:00:00'+NUMTODSINTERVAL(n,'HOUR'),
       NULL,
       'Assigned'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO SENSOR_READING
SELECT 920000+n,
       920000+n,
       TIMESTAMP '2026-11-04 09:00:00'+NUMTODSINTERVAL(n,'HOUR'),
       CASE MOD(n,3) WHEN 0 THEN -18.5 WHEN 1 THEN 5.2 ELSE 6.1 END,
       40+n,
       13.0827+n/1000,
       80.2707+n/1000,
       95-n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO TEMPERATURE_ALERT
SELECT 920000+n,
       920000+n,
       920000+n,
       TIMESTAMP '2026-11-04 10:00:00'+NUMTODSINTERVAL(n,'HOUR'),
       'Temperature Deviation',
       CASE MOD(n,3) WHEN 0 THEN -12 ELSE 9 END,
       CASE MOD(n,3) WHEN 0 THEN -25 ELSE 2 END,
       CASE MOD(n,3) WHEN 0 THEN -15 ELSE 8 END,
       CASE MOD(n,2) WHEN 0 THEN 'High' ELSE 'Medium' END,
       CASE MOD(n,2) WHEN 0 THEN 'Open' ELSE 'Acknowledged' END,
       CASE MOD(n,2) WHEN 0 THEN NULL ELSE TIMESTAMP '2026-11-04 11:00:00' END
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO COLD_CHAIN_INCIDENT
SELECT 920000+n,
       920000+n,
       920000+n,
       'Temperature Excursion',
       DATE '2026-11-04'+n,
       'Temperature deviation incident '||n,
       CASE MOD(n,2) WHEN 0 THEN 'High' ELSE 'Medium' END,
       'Product quality assessment required',
       CASE MOD(n,2) WHEN 0 THEN 'Open' ELSE 'Under Review' END,
       NULL,
       'Inspect shipment and verify product quality'
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

INSERT INTO DELIVERY
SELECT 920000+n,
       920000+n,
       920000+n,
       DATE '2026-11-05'+n,
       'Receiving Officer '||n,
       CASE MOD(n,3) WHEN 0 THEN 'Pending' WHEN 1 THEN 'In Transit' ELSE 'Scheduled' END,
       0,
       0,
       NULL,
       'Delivery record '||n
FROM (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 15);

COMMIT;

SELECT COUNT(*) FROM MANUFACTURER;
SELECT COUNT(*) FROM PHARMACEUTICAL_PRODUCT;
SELECT COUNT(*) FROM PRODUCT_BATCH;
SELECT COUNT(*) FROM QUALITY_TEST;
SELECT COUNT(*) FROM WAREHOUSE;
SELECT COUNT(*) FROM STORAGE_UNIT;
SELECT COUNT(*) FROM INVENTORY;
SELECT COUNT(*) FROM INVENTORY_TRANSACTION;
SELECT COUNT(*) FROM VEHICLE;
SELECT COUNT(*) FROM DRIVER;
SELECT COUNT(*) FROM ROUTE;
SELECT COUNT(*) FROM ROUTE_STOP;
SELECT COUNT(*) FROM IOT_SENSOR;
SELECT COUNT(*) FROM SENSOR_READING;
SELECT COUNT(*) FROM SHIPMENT;
SELECT COUNT(*) FROM SHIPMENT_ITEM;
SELECT COUNT(*) FROM VEHICLE_ASSIGNMENT;
SELECT COUNT(*) FROM TEMPERATURE_ALERT;
SELECT COUNT(*) FROM COLD_CHAIN_INCIDENT;
SELECT COUNT(*) FROM DELIVERY;
SELECT COUNT(*) FROM HEALTHCARE_FACILITY;
SELECT COUNT(*) FROM DISTRIBUTION_CENTER;
SELECT COUNT(*) FROM STORAGE_CONDITION;