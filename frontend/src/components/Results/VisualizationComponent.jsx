import React from 'react';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    LineChart,
    Line,
    AreaChart,
    Area
} from 'recharts';
import { Box, Typography, Paper, useTheme } from '@mui/material';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658'];

const VisualizationComponent = ({ data, config }) => {
    const theme = useTheme();
    const isDark = theme.palette.mode === 'dark';

    if (!data || data.length === 0) {
        return (
            <Box sx={{ p: 4, textAlign: 'center' }}>
                <Typography color="text.secondary">No data available for visualization</Typography>
            </Box>
        );
    }

    const configData = config || {};
    const chart_type = configData.chart_type || configData.chartType;
    const title = configData.title;
    const configX = configData.x_key || configData.xKey;
    const configY = configData.y_key || configData.yKey;

    const isNumeric = (value) => typeof value === 'number' && Number.isFinite(value);
    const toLabel = (value) => {
        if (value === null || value === undefined) return 'Unknown';
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
            return String(value);
        }
        if (Array.isArray(value)) {
            return value.map((v) => toLabel(v)).join(', ');
        }
        if (typeof value === 'object') {
            // Prefer common semantic keys if present
            for (const key of ['label', 'name', 'category', 'status', 'country', 'state', 'x', 'y']) {
                if (value[key] !== undefined && value[key] !== null) {
                    return String(value[key]);
                }
            }
            try {
                return Object.entries(value)
                    .map(([k, v]) => `${k}: ${toLabel(v)}`)
                    .join(' | ');
            } catch {
                return 'Unknown';
            }
        }
        return String(value);
    };
    const isDateLike = (value) => {
        if (value instanceof Date) return true;
        if (typeof value !== 'string') return false;
        // ISO-ish timestamps or date strings
        return /^\d{4}-\d{2}-\d{2}/.test(value) || /\d{1,2}\/\d{1,2}\/\d{4}/.test(value);
    };

    // Helper to intelligently detect keys if AI didn't provide them or got them wrong
    const getKeys = () => {
        const sample = data[0];
        const keys = Object.keys(sample);

        let x = configX || (sample.hasOwnProperty('label') ? 'label' : '_id');
        let y = configY || (sample.hasOwnProperty('value') ? 'value' : (sample.hasOwnProperty('count') ? 'count' : null));

        // If explicitly requested fields exist in data, use them
        if (configX && !sample.hasOwnProperty(configX)) {
            // Check if AI used 'label' but config has something else, or vice-versa
            if (sample.hasOwnProperty('label')) x = 'label';
            else x = keys.find(k => k.toLowerCase().includes('name') || k.toLowerCase().includes('label') || k === '_id') || keys[0];
        }
        if (configY && !sample.hasOwnProperty(configY)) {
            if (sample.hasOwnProperty('value')) y = 'value';
            else y = keys.find(k => k !== x && isNumeric(sample[k])) || keys.find(k => k !== x) || keys[1];
        }

        // Prefer semantically strong numeric fields for Y when auto mode is used.
        if (!configY) {
            const preferredNumeric = [
                'value', 'count', 'total', 'total_amount', 'amount', 'revenue',
                'stock', 'quantity', 'price', 'sum'
            ];
            const preferredY = keys.find((k) =>
                preferredNumeric.includes(k.toLowerCase()) && isNumeric(sample[k])
            );
            if (preferredY) y = preferredY;
        }

        // Prefer numeric Y if current guess is missing/non-numeric
        if (!y || !isNumeric(sample[y])) {
            y = keys.find(k => k !== x && isNumeric(sample[k])) || y || keys.find(k => k !== x) || keys[0];
        }

        // Prefer meaningful categorical X when auto mode is used.
        if (!configX) {
            const preferredCategorical = [
                'label', 'status', 'category', 'category_name', 'name', 'type',
                'country', 'state', 'city', 'customer_name', 'month', 'year', 'date'
            ];

            const preferredX = keys.find((k) =>
                preferredCategorical.includes(k.toLowerCase()) &&
                !isNumeric(sample[k])
            );

            if (preferredX) {
                x = preferredX;
            } else {
                // Fallback to categorical key with best grouping potential
                const nonNumericKeys = keys.filter((k) => !isNumeric(sample[k]));
                const ranked = nonNumericKeys
                    .map((k) => {
                        const vals = data.map((row) => row?.[k]).filter((v) => v !== null && v !== undefined);
                        const unique = new Set(vals.map((v) => String(v))).size;
                        const total = vals.length || 1;
                        const duplicateRatio = 1 - unique / total;
                        const datePenalty = vals.length > 0 && vals.every((v) => isDateLike(v)) ? -1 : 0;
                        return { k, score: duplicateRatio + datePenalty };
                    })
                    .sort((a, b) => b.score - a.score);

                if (ranked.length > 0 && ranked[0].score > -0.5) {
                    x = ranked[0].k;
                } else {
                    // Final fallback: pick any key different from Y
                    const fallbackX = keys.find((k) => k !== y);
                    if (fallbackX) x = fallbackX;
                }
            }
        }

        // AUTO-DETECTION: Ensure Y is numeric and X is label/category
        // If Y is a string and X is a number, flip them!
        if (typeof sample[y] === 'string' && isNumeric(sample[x])) {
            [x, y] = [y, x];
        }

        return { x, y };
    };

    const { x, y } = getKeys();
    const rawChartData = data;

    // For fallback charts on tabular results, aggregate duplicate categories so bars/pies are meaningful.
    const shouldAggregateByCategory =
        ['bar', 'pie', 'doughnut'].includes(chart_type) &&
        rawChartData.length > 1 &&
        rawChartData.every((row) => row && row[x] !== undefined) &&
        rawChartData.filter((row) => row && row[x] !== undefined).length !== new Set(rawChartData.map((row) => String(row[x]))).size;

    const chartData = shouldAggregateByCategory
        ? Array.from(
            rawChartData.reduce((map, row) => {
                const label = toLabel(row?.[x]);
                const value = Number(row?.[y]);
                const prev = map.get(label) || 0;
                map.set(label, prev + (Number.isFinite(value) ? value : 0));
                return map;
            }, new Map()).entries()
        ).map(([label, value]) => ({ [x]: label, [y]: value }))
        : rawChartData.map((row) => {
            const safeRow = { ...row };
            safeRow[x] = toLabel(row?.[x]);
            const yVal = Number(row?.[y]);
            if (Number.isFinite(yVal)) safeRow[y] = yVal;
            return safeRow;
        });

    const renderChart = () => {
        switch (chart_type) {
            case 'pie':
                return (
                    <PieChart>
                        <Pie
                            data={chartData}
                            cx="50%"
                            cy="50%"
                            labelLine={true}
                            label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                            outerRadius={120}
                            fill="#8884d8"
                            dataKey={y}
                            nameKey={x}
                        >
                            {chartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{
                                backgroundColor: isDark ? '#1e293b' : '#fff',
                                borderColor: theme.palette.divider,
                                color: theme.palette.text.primary
                            }}
                        />
                        <Legend />
                    </PieChart>
                );

            case 'bar':
                return (
                    <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'} />
                        <XAxis
                            dataKey={x}
                            stroke={theme.palette.text.secondary}
                            fontSize={12}
                            angle={-45}
                            textAnchor="end"
                            interval={0}
                        />
                        <YAxis
                            stroke={theme.palette.text.secondary}
                            fontSize={12}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: isDark ? '#1e293b' : '#fff',
                                borderColor: theme.palette.divider,
                                color: theme.palette.text.primary
                            }}
                        />
                        <Legend verticalAlign="top" height={36} />
                        <Bar dataKey={y} fill={theme.palette.primary.main} radius={[4, 4, 0, 0]} />
                    </BarChart>
                );

            case 'line':
                return (
                    <LineChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'} />
                        <XAxis
                            dataKey={x}
                            stroke={theme.palette.text.secondary}
                            fontSize={12}
                            angle={-45}
                            textAnchor="end"
                        />
                        <YAxis stroke={theme.palette.text.secondary} fontSize={12} />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: isDark ? '#1e293b' : '#fff',
                                borderColor: theme.palette.divider,
                                color: theme.palette.text.primary
                            }}
                        />
                        <Legend verticalAlign="top" height={36} />
                        <Line type="monotone" dataKey={y} stroke={theme.palette.primary.main} strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    </LineChart>
                );

            case 'area':
                return (
                    <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'} />
                        <XAxis
                            dataKey={x}
                            stroke={theme.palette.text.secondary}
                            fontSize={12}
                            angle={-45}
                            textAnchor="end"
                        />
                        <YAxis stroke={theme.palette.text.secondary} fontSize={12} />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: isDark ? '#1e293b' : '#fff',
                                borderColor: theme.palette.divider,
                                color: theme.palette.text.primary
                            }}
                        />
                        <Legend verticalAlign="top" height={36} />
                        <Area type="monotone" dataKey={y} stroke={theme.palette.primary.main} fill={theme.palette.primary.main} fillOpacity={0.3} />
                    </AreaChart>
                );

            default:
                return <Typography>Unsupported chart type: {chart_type}</Typography>;
        }
    };

    return (
        <Paper elevation={0} sx={{ p: 2, height: '100%', backgroundColor: 'transparent' }}>
            {title && (
                <Typography variant="h6" align="center" gutterBottom fontWeight="bold">
                    {title}
                </Typography>
            )}
            <Box sx={{ width: '100%', height: 400, mt: 2 }}>
                <ResponsiveContainer>
                    {renderChart()}
                </ResponsiveContainer>
            </Box>
        </Paper>
    );
};

export default VisualizationComponent;
