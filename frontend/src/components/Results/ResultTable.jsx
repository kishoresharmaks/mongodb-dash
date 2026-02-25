import React, { useState } from 'react';
import {
    Box,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Typography,
    Button,
    Chip,
    Tooltip
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import StarIcon from '@mui/icons-material/Star';

const ResultTable = ({ results }) => {
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(20);

    if (!results || results.length === 0) {
        return (
            <Box sx={{ p: 4, textAlign: 'center', backgroundColor: 'action.hover', borderRadius: 2 }}>
                <Typography variant="body1" color="text.secondary">
                    No results found for this query.
                </Typography>
            </Box>
        );
    }

    // Get column headers from all results (not just first, to handle partial docs)
    const columns = [...new Set(results.flatMap(r => (r && typeof r === 'object' ? Object.keys(r) : [])))];

    // Fallback: if columns could not be determined, show raw JSON
    if (columns.length === 0) {
        return (
            <Box sx={{ p: 3 }}>
                <Chip label={`${results.length} total results`} size="small" color="primary" sx={{ mb: 2 }} />
                {results.map((row, i) => (
                    <Box key={i} sx={{ mb: 1, p: 2, bgcolor: 'action.hover', borderRadius: 1, fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                        {JSON.stringify(row, null, 2)}
                    </Box>
                ))}
            </Box>
        );
    }

    const handleChangePage = (event, newPage) => {
        setPage(newPage);
    };

    const handleChangeRowsPerPage = (event) => {
        setRowsPerPage(parseInt(event.target.value, 10));
        setPage(0);
    };

    // Helper to format cell content based on column name and value type
    const formatCellContent = (column, value) => {
        if (value === null || value === undefined) return '-';

        // Column-specific formatting
        if (column === 'genres' || column === 'directors' || column === 'cast') {
            const list = Array.isArray(value) ? value : [value];
            return (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {list.map((item, idx) => (
                        <Chip key={idx} label={item} size="small" variant="outlined" />
                    ))}
                </Box>
            );
        }

        if (column === 'imdb') {
            return (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <StarIcon sx={{ color: '#faaf00', fontSize: 16 }} />
                    <Typography variant="body2" fontWeight="bold">
                        {value.rating || 'N/A'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                        ({value.votes || 0})
                    </Typography>
                </Box>
            );
        }

        if (column === 'plot' || column === 'fullplot') {
            return (
                <Tooltip title={value} placement="top">
                    <Typography
                        variant="body2"
                        sx={{
                            maxWidth: 300,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis'
                        }}
                    >
                        {value}
                    </Typography>
                </Tooltip>
            );
        }

        if (column === '_id') {
            const strVal = String(value);
            return (
                <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                    {strVal.length > 8 ? strVal.substring(0, 8) + '...' : strVal}
                </Typography>
            );
        }

        // Format ISO date strings nicely
        if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
            try {
                return new Date(value).toLocaleString();
            } catch { /* fall through */ }
        }

        // Helper: extract a readable label from an object
        const getObjectLabel = (obj) => {
            if (typeof obj !== 'object' || obj === null) return String(obj);
            const labelFields = ['name', 'title', 'product_name', 'label', 'first_name', 'username', 'email'];
            for (const field of labelFields) {
                if (obj[field] !== undefined && obj[field] !== null) return String(obj[field]);
            }
            // Fall back to first string value in the object
            const firstStr = Object.values(obj).find((v) => typeof v === 'string');
            if (firstStr) return firstStr;
            return JSON.stringify(obj);
        };

        // Type-based formatting
        if (Array.isArray(value)) {
            if (value.length === 0) return '-';
            if (typeof value[0] === 'object' && value[0] !== null) {
                // Array of objects — render each as a labelled chip
                return (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {value.map((item, idx) => (
                            <Chip key={idx} label={getObjectLabel(item)} size="small" variant="outlined" />
                        ))}
                    </Box>
                );
            }
            // Array of primitives — render as chips
            return (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {value.map((item, idx) => (
                        <Chip key={idx} label={String(item)} size="small" variant="outlined" />
                    ))}
                </Box>
            );
        }

        if (typeof value === 'object') {
            // Plain object — show non-nested key:value pairs (max 3)
            const entries = Object.entries(value)
                .filter(([, v]) => typeof v !== 'object')
                .slice(0, 3);
            if (entries.length > 0) {
                return entries.map(([k, v]) => `${k}: ${v}`).join(' | ');
            }
            return JSON.stringify(value);
        }

        return String(value);
    };

    const exportToCSV = () => {
        const headers = columns.join(',');
        const rows = results.map((row) =>
            columns.map((col) => {
                const value = row[col];
                if (typeof value === 'object' && value !== null) {
                    return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
                }
                return `"${String(value).replace(/"/g, '""')}"`;
            }).join(',')
        );

        const csv = [headers, ...rows].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `query-results-${new Date().getTime()}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
    };

    const paginatedResults = results.slice(
        page * rowsPerPage,
        page * rowsPerPage + rowsPerPage
    );

    return (
        <Paper elevation={3} sx={{ borderRadius: 2, overflow: 'hidden' }}>
            <Box sx={{ p: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid', borderColor: 'divider' }}>
                <Box>
                    <Typography variant="h6" fontWeight="bold">Query Results</Typography>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.5 }}>
                        <Chip label={`${results.length} total results`} size="small" color="primary" />
                        <Typography variant="caption" color="text.secondary">
                            Showing page {page + 1} of {Math.ceil(results.length / rowsPerPage)}
                        </Typography>
                    </Box>
                </Box>
                <Button
                    startIcon={<DownloadIcon />}
                    onClick={exportToCSV}
                    variant="contained"
                    size="small"
                    sx={{ borderRadius: 2 }}
                >
                    Export CSV
                </Button>
            </Box>

            <TableContainer sx={{ maxHeight: 500 }}>
                <Table stickyHeader size="medium">
                    <TableHead>
                        <TableRow>
                            {columns.map((column) => (
                                <TableCell
                                    key={column}
                                    sx={{
                                        fontWeight: 'bold',
                                        backgroundColor: 'background.paper',
                                        textTransform: 'uppercase',
                                        fontSize: '0.75rem',
                                        letterSpacing: '0.05em',
                                        color: 'text.secondary'
                                    }}
                                >
                                    {column.replace('_', ' ')}
                                </TableCell>
                            ))}
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {paginatedResults.map((row, index) => (
                            <TableRow key={index} hover sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                                {columns.map((column) => (
                                    <TableCell key={column}>
                                        {formatCellContent(column, row[column])}
                                    </TableCell>
                                ))}
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>

            <TablePagination
                rowsPerPageOptions={[10, 20, 50, 100]}
                component="div"
                count={results.length}
                rowsPerPage={rowsPerPage}
                page={page}
                onPageChange={handleChangePage}
                onRowsPerPageChange={handleChangeRowsPerPage}
                sx={{ borderTop: '1px solid', borderColor: 'divider' }}
            />
        </Paper>
    );
};

export default ResultTable;
