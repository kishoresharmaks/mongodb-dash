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

    // Helper to intelligently detect keys if AI didn't provide them or got them wrong
    const getKeys = () => {
        const sample = data[0];
        const keys = Object.keys(sample);

        let x = configX || (sample.hasOwnProperty('label') ? 'label' : '_id');
        let y = configY || (sample.hasOwnProperty('value') ? 'value' : (sample.hasOwnProperty('count') ? 'count' : 'results'));

        // If explicitly requested fields exist in data, use them
        if (configX && !sample.hasOwnProperty(configX)) {
            // Check if AI used 'label' but config has something else, or vice-versa
            if (sample.hasOwnProperty('label')) x = 'label';
            else x = keys.find(k => k.toLowerCase().includes('name') || k.toLowerCase().includes('label') || k === '_id') || keys[0];
        }
        if (configY && !sample.hasOwnProperty(configY)) {
            if (sample.hasOwnProperty('value')) y = 'value';
            else y = keys.find(k => k !== x && typeof sample[k] === 'number') || keys.find(k => k !== x) || keys[1];
        }

        // AUTO-DETECTION: Ensure Y is numeric and X is label/category
        // If Y is a string and X is a number, flip them!
        if (typeof sample[y] === 'string' && typeof sample[x] === 'number') {
            [x, y] = [y, x];
        }

        return { x, y };
    };

    const { x, y } = getKeys();

    const renderChart = () => {
        switch (chart_type) {
            case 'pie':
                return (
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="50%"
                            labelLine={true}
                            label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                            outerRadius={120}
                            fill="#8884d8"
                            dataKey={y}
                            nameKey={x}
                        >
                            {data.map((entry, index) => (
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
                    <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
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
                    <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
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
                    <AreaChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
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
