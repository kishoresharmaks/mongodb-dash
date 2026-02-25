import React, { useState } from 'react';
import {
    Box,
    TextField,
    IconButton,
    CircularProgress,
    ToggleButtonGroup,
    ToggleButton,
    Tooltip,
    Chip,
    Divider
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import BarChartIcon from '@mui/icons-material/BarChart';
import PieChartIcon from '@mui/icons-material/PieChart';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import TimelineIcon from '@mui/icons-material/Timeline';
import TableChartIcon from '@mui/icons-material/TableChart';

const InputBox = ({ onSend, loading, debugMode = 'auto', onDebugModeChange }) => {
    const [query, setQuery] = useState('');
    const [visualizationMode, setVisualizationMode] = useState('data'); // 'data' = data only, 'bar', 'pie', etc.

    const handleSubmit = (e) => {
        e.preventDefault();
        if (query.trim() && !loading) {
            // Send query with visualization preferences
            onSend(query, {
                visualize: visualizationMode !== 'data' && visualizationMode !== null,
                chartType: visualizationMode === 'data' ? null : visualizationMode,
                debugMode: debugMode // NEW: Pass debug mode preference
            });
            setQuery('');
            setVisualizationMode('data'); // Reset to data-only after send
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    const handleVisualizationChange = (event, newMode) => {
        setVisualizationMode(newMode);
    };

    const handleDebugModeChange = (event, newMode) => {
        if (newMode !== null) {
            if (onDebugModeChange) onDebugModeChange(newMode);
        }
    };

    return (
        <Box
            component="form"
            onSubmit={handleSubmit}
            sx={{
                p: 2,
                backgroundColor: 'background.default',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center'
            }}
        >
            {/* Main Input Container */}
            <Box sx={{
                display: 'flex',
                flexDirection: 'column',
                gap: 1.5,
                width: '100%',
                maxWidth: 800,
                p: 1.5,
                backgroundColor: 'background.paper',
                borderRadius: 4,
                boxShadow: (theme) => theme.palette.mode === 'dark' ? '0 8px 30px rgba(0,0,0,0.4)' : '0 8px 30px rgba(0,0,0,0.08)',
                border: (theme) => `1px solid ${theme.palette.divider}`,
            }}>
                {/* Text Input */}
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                    <TextField
                        fullWidth
                        multiline
                        maxRows={4}
                        placeholder="Ask a question about your database..."
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyPress={handleKeyPress}
                        disabled={loading}
                        variant="standard"
                        InputProps={{
                            disableUnderline: true,
                            sx: { px: 1, py: 0.5 }
                        }}
                        inputProps={{ maxLength: 5000 }}
                    />
                    <IconButton
                        type="submit"
                        color="primary"
                        disabled={!query.trim() || loading}
                        sx={{
                            backgroundColor: (theme) => query.trim() ? theme.palette.primary.main : 'transparent',
                            color: (theme) => query.trim() ? '#fff' : 'inherit',
                            '&:hover': {
                                backgroundColor: (theme) => theme.palette.primary.dark,
                            },
                            width: 45,
                            height: 45
                        }}
                    >
                        {loading ? <CircularProgress size={24} color="inherit" /> : <SendIcon />}
                    </IconButton>
                </Box>

                <Divider />

                {/* Visualization Controls */}
                <Box sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 2,
                    flexWrap: 'wrap'
                }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip
                            label="Output:"
                            size="small"
                            sx={{
                                fontWeight: 600,
                                fontSize: '0.7rem',
                                letterSpacing: 0.5
                            }}
                        />
                        <ToggleButtonGroup
                            value={visualizationMode}
                            exclusive
                            onChange={handleVisualizationChange}
                            size="small"
                            sx={{
                                gap: 0.5,
                                '& .MuiToggleButton-root': {
                                    border: 1,
                                    borderRadius: 2,
                                    px: 1.5,
                                    py: 0.5,
                                    fontSize: '0.75rem',
                                    textTransform: 'none',
                                    '&.Mui-selected': {
                                        backgroundColor: 'primary.main',
                                        color: '#fff',
                                        '&:hover': {
                                            backgroundColor: 'primary.dark',
                                        }
                                    }
                                }
                            }}
                        >
                            <ToggleButton value="data">
                                <Tooltip title="Return data in table format">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        <TableChartIcon fontSize="small" />
                                        Data
                                    </Box>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="bar">
                                <Tooltip title="Bar Chart - Great for comparing categories">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        <BarChartIcon fontSize="small" />
                                        Bar
                                    </Box>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="pie">
                                <Tooltip title="Pie Chart - Shows proportions">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        <PieChartIcon fontSize="small" />
                                        Pie
                                    </Box>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="line">
                                <Tooltip title="Line Chart - Best for trends over time">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        <ShowChartIcon fontSize="small" />
                                        Line
                                    </Box>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="area">
                                <Tooltip title="Area Chart - Shows cumulative trends">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                        <TimelineIcon fontSize="small" />
                                        Area
                                    </Box>
                                </Tooltip>
                            </ToggleButton>
                        </ToggleButtonGroup>
                    </Box>

                    {/* Debug Mode Toggle */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip
                            label="🔧 Debug:"
                            size="small"
                            color="warning"
                            variant="outlined"
                            sx={{
                                fontWeight: 600,
                                fontSize: '0.7rem',
                                letterSpacing: 0.5
                            }}
                        />
                        <ToggleButtonGroup
                            value={debugMode}
                            exclusive
                            onChange={handleDebugModeChange}
                            size="small"
                            sx={{
                                '& .MuiToggleButton-root': {
                                    border: 1,
                                    borderRadius: 2,
                                    px: 1.5,
                                    py: 0.5,
                                    fontSize: '0.7rem',
                                    textTransform: 'none',
                                    '&.Mui-selected': {
                                        backgroundColor: 'warning.main',
                                        color: '#fff',
                                        '&:hover': {
                                            backgroundColor: 'warning.dark',
                                        }
                                    }
                                }
                            }}
                        >
                            <ToggleButton value="auto">
                                <Tooltip title="Auto: Use smart templates when chart type is selected, otherwise use LLM">
                                    <span>Auto</span>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="llm">
                                <Tooltip title="Force LLM: Always use AI to generate MQL (slower, flexible)">
                                    <span>🤖 LLM</span>
                                </Tooltip>
                            </ToggleButton>
                            <ToggleButton value="template">
                                <Tooltip title="Force Templates: Always use hardcoded patterns (fast, reliable)">
                                    <span>📋 Template</span>
                                </Tooltip>
                            </ToggleButton>
                        </ToggleButtonGroup>
                    </Box>
                </Box>
            </Box>
        </Box>
    );
};

export default InputBox;
