import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Button,
    Chip,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    IconButton,
    Snackbar,
    Alert,
    Tabs,
    Tab,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    CircularProgress
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import SecurityIcon from '@mui/icons-material/Security';
import PeopleIcon from '@mui/icons-material/People';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import api from '../../services/api';

const AdminPortal = () => {
    const [tab, setTab] = useState(0);
    const [users, setUsers] = useState([]);
    const [policies, setPolicies] = useState([]);
    const [loading, setLoading] = useState(false);
    const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });

    // AI Config Builder state
    const [configMode, setConfigMode] = useState('guided'); // 'guided' or 'expert'
    const [aiIdentity, setAiIdentity] = useState({
        role: 'MongoDB query expert and assistant',
        tone: 'professional and technical',
        customRules: ['Use proper MongoDB operators ($eq, $gt, $lt, etc.)', 'Always return result in valid JSON']
    });
    const [systemPrompt, setSystemPrompt] = useState('');
    const [savingConfig, setSavingConfig] = useState(false);

    // Policy Builder UI state
    const [policyDialog, setPolicyDialog] = useState(false);
    const [currentPolicy, setCurrentPolicy] = useState({
        name: '',
        description: '',
        permissions: { collections: [] }
    });

    // User form state
    const [userDialog, setUserDialog] = useState(false);
    const [currentUser, setCurrentUser] = useState({
        _id: '',
        name: '',
        role: '',
        rolePolicy: ''
    });

    const [fetchedCollections, setFetchedCollections] = useState([]);
    const [resetting, setResetting] = useState(false);

    useEffect(() => {
        fetchMetadata();
        if (tab === 2) {
            fetchSystemConfig();
        } else {
            fetchData();
        }
    }, [tab]);

    const fetchMetadata = async () => {
        try {
            const res = await api.get('/admin/metadata/collections');
            setFetchedCollections(res.data.data);
        } catch (err) {
            console.error('Metadata fetch failed:', err);
        }
    };

    // Automatic Prompt Compiler for Guided Mode
    useEffect(() => {
        if (configMode === 'guided' && systemPrompt.includes('{permission_text}')) {
            // We already have a prompt in the box, don't overwrite it unless it's the default
        }
    }, [aiIdentity, configMode]);

    const compilePrompt = () => {
        return `You are a ${aiIdentity.role}. Your tone should be ${aiIdentity.tone}.

{permission_text}

{history_text}

TASK 1: CLASSIFY THE QUERY
Determine the intent. PRIORITY: Visualization > Database > Conversational.

1. IF IT IS A VISUALIZATION REQUEST:
You MUST return "type": "visualization".
{
    "type": "visualization",
    "chart_type": "pie", "bar", "line", or "area",
    "title": "Descriptive Title",
    "x_key": "category_field",
    "y_key": "numeric_field",
    "mql": { "collection": "name", "operation": "aggregate", "pipeline": [...] }
}

2. IF IT IS A DATABASE QUERY:
{ "type": "database", "mql": { "collection": "name", "operation": "find", "query": {} } }

3. IF IT IS A CONVERSATIONAL QUESTION:
{ "type": "conversational", "response": "..." }

Rules and Guidelines:
${aiIdentity.customRules.map((r, i) => `${i + 1}. ${r}`).join('\n')}

Database: {database_name}
Available Collections: {collections_list}
Context: {current_collection}

Result (JSON):`;
    };

    const fetchData = async () => {
        setLoading(true);
        try {
            if (tab === 0) {
                const res = await api.get('/admin/users');
                setUsers(res.data.data);
            } else {
                fetchPolicies();
            }
        } catch (err) {
            showSnackbar('Error fetching data', 'error');
        } finally {
            setLoading(false);
        }
    };

    const fetchPolicies = async () => {
        try {
            const res = await api.get('/admin/policies');
            setPolicies(res.data.data);
        } catch (err) {
            showSnackbar('Error fetching policies', 'error');
        }
    };

    const fetchSystemConfig = async () => {
        setLoading(true);
        try {
            const res = await api.get('/admin/config/main_system_prompt');
            setSystemPrompt(res.data.data.value || '');
        } catch (err) {
            showSnackbar('Error fetching system prompt', 'error');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveConfig = async () => {
        setSavingConfig(true);
        try {
            await api.post('/admin/config', {
                key: 'main_system_prompt',
                value: systemPrompt,
                description: 'Main AI assistant system instructions'
            });
            showSnackbar('AI configuration updated successfully');
        } catch (err) {
            showSnackbar('Error saving configuration', 'error');
        } finally {
            setSavingConfig(false);
        }
    };

    const handleResetConfig = async () => {
        if (!window.confirm('Are you sure you want to revert to factory settings? This will delete all custom AI rules.')) return;

        setResetting(true);
        try {
            await api.post('/admin/config/reset', { key: 'main_system_prompt' });
            await fetchSystemConfig();
            showSnackbar('AI personality reset to factory defaults');
        } catch (err) {
            showSnackbar('Error resetting configuration', 'error');
        } finally {
            setResetting(false);
        }
    };

    const showSnackbar = (message, severity = 'success') => {
        setSnackbar({ open: true, message, severity });
    };

    const handleSavePolicy = async () => {
        try {
            if (currentPolicy._id) {
                await api.put(`/admin/policies/${currentPolicy._id}`, currentPolicy);
            } else {
                await api.post('/admin/policies', currentPolicy);
            }
            showSnackbar('Policy saved successfully');
            setPolicyDialog(false);
            fetchData();
        } catch (err) {
            showSnackbar('Error saving policy', 'error');
        }
    };

    const handleEditUser = (user) => {
        setCurrentUser({
            _id: user._id,
            name: user.name,
            role: user.role || 'Analyst',
            rolePolicy: user.rolePolicy || ''
        });
        setUserDialog(true);
    };

    const handleSaveUserRole = async () => {
        try {
            await api.put(`/admin/users/${currentUser._id}/role`, {
                role: currentUser.role,
                rolePolicy: currentUser.rolePolicy
            });
            showSnackbar('User role updated successfully');
            setUserDialog(false);
            fetchData();
        } catch (err) {
            showSnackbar('Error updating user role', 'error');
        }
    };

    return (
        <Box sx={{ p: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
                <SecurityIcon color="primary" sx={{ fontSize: 40 }} />
                <Typography variant="h4" fontWeight="800">Governance Control Center</Typography>
            </Box>

            <Tabs value={tab} onChange={(e, n) => setTab(n)} sx={{ mb: 3 }}>
                <Tab icon={<PeopleIcon />} label="User Management" />
                <Tab icon={<SecurityIcon />} label="Role Policies" />
                <Tab icon={<SmartToyIcon />} label="AI Configuration" />
            </Tabs>

            {loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 8 }}><CircularProgress /></Box>
            ) : tab === 0 ? (
                <TableContainer component={Paper} elevation={3}>
                    <Table>
                        <TableHead>
                            <TableRow>
                                <TableCell>Name</TableCell>
                                <TableCell>Email</TableCell>
                                <TableCell>Current Role</TableCell>
                                <TableCell>Policy Linked</TableCell>
                                <TableCell>Actions</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {users.map((user) => (
                                <TableRow key={user._id}>
                                    <TableCell>{user.name}</TableCell>
                                    <TableCell>{user.email}</TableCell>
                                    <TableCell>
                                        <Chip
                                            label={user.role}
                                            color={user.role === 'admin' ? 'secondary' : 'primary'}
                                            variant="outlined"
                                        />
                                    </TableCell>
                                    <TableCell>
                                        {policies.find(p => p._id === user.rolePolicy)?.name || 'None'}
                                    </TableCell>
                                    <TableCell>
                                        <Button
                                            startIcon={<EditIcon />}
                                            size="small"
                                            onClick={() => handleEditUser(user)}
                                        >
                                            Edit Role
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </TableContainer>
            ) : tab === 1 ? (
                <Box>
                    <Button
                        variant="contained"
                        sx={{ mb: 2 }}
                        onClick={() => {
                            setCurrentPolicy({ name: '', description: '', permissions: { collections: [] } });
                            setPolicyDialog(true);
                        }}
                    >
                        Create New Role
                    </Button>
                    <TableContainer component={Paper} elevation={3}>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Role Name</TableCell>
                                    <TableCell>Description</TableCell>
                                    <TableCell>Status</TableCell>
                                    <TableCell>Actions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {policies.map((p) => (
                                    <TableRow key={p._id}>
                                        <TableCell><strong>{p.name}</strong></TableCell>
                                        <TableCell>{p.description}</TableCell>
                                        <TableCell>
                                            {p.isDefault && <Chip label="Default" size="small" color="success" />}
                                        </TableCell>
                                        <TableCell>
                                            <IconButton onClick={() => {
                                                setCurrentPolicy(p);
                                                setPolicyDialog(true);
                                            }}>
                                                <EditIcon />
                                            </IconButton>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </Box>
            ) : (
                <Box>
                    <Box sx={{ mb: 3, display: 'flex', gap: 2 }}>
                        <Button
                            variant={configMode === 'guided' ? 'contained' : 'outlined'}
                            onClick={() => setConfigMode('guided')}
                            startIcon={<SmartToyIcon />}
                        >
                            Guided Builder (Easy)
                        </Button>
                        <Button
                            variant={configMode === 'expert' ? 'contained' : 'outlined'}
                            onClick={() => setConfigMode('expert')}
                        >
                            Developer Console (Expert)
                        </Button>
                    </Box>

                    {configMode === 'guided' ? (
                        <Paper sx={{ p: 4, elevation: 3 }}>
                            <Typography variant="h6" gutterBottom color="primary">AI Assistant Identity</Typography>
                            <Box sx={{ display: 'flex', gap: 3, mb: 4 }}>
                                <TextField
                                    fullWidth
                                    label="Who is the AI? (e.g. Movie Database Expert)"
                                    value={aiIdentity.role}
                                    onChange={(e) => setAiIdentity({ ...aiIdentity, role: e.target.value })}
                                />
                                <FormControl fullWidth>
                                    <InputLabel>Tone of Voice</InputLabel>
                                    <Select
                                        value={aiIdentity.tone}
                                        label="Tone of Voice"
                                        onChange={(e) => setAiIdentity({ ...aiIdentity, tone: e.target.value })}
                                    >
                                        <MenuItem value="professional and technical">Professional & Technical</MenuItem>
                                        <MenuItem value="friendly and conversational">Friendly & Conversational</MenuItem>
                                        <MenuItem value="concise and direct">Concise & Direct</MenuItem>
                                        <MenuItem value="a helpful pirate">Fun (Pirate!)</MenuItem>
                                    </Select>
                                </FormControl>
                            </Box>

                            <Typography variant="h6" gutterBottom color="primary">Custom Intelligence Rules</Typography>
                            <Box sx={{ mb: 3 }}>
                                {aiIdentity.customRules.map((rule, index) => (
                                    <Chip
                                        key={index}
                                        label={rule}
                                        onDelete={() => {
                                            const newRules = aiIdentity.customRules.filter((_, i) => i !== index);
                                            setAiIdentity({ ...aiIdentity, customRules: newRules });
                                        }}
                                        sx={{ mr: 1, mb: 1 }}
                                    />
                                ))}
                            </Box>
                            <TextField
                                fullWidth
                                label="Add a new business rule (e.g. Never show user passwords)"
                                placeholder="Press Enter to add"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && e.target.value) {
                                        setAiIdentity({ ...aiIdentity, customRules: [...aiIdentity.customRules, e.target.value] });
                                        e.target.value = '';
                                    }
                                }}
                                sx={{ mb: 4 }}
                            />

                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2 }}>
                                <Button
                                    color="error"
                                    variant="outlined"
                                    onClick={handleResetConfig}
                                    disabled={resetting}
                                >
                                    {resetting ? <CircularProgress size={20} /> : 'Restore Factory Defaults'}
                                </Button>
                                <Box sx={{ display: 'flex', gap: 2 }}>
                                    <Button
                                        variant="contained"
                                        size="large"
                                        onClick={() => {
                                            const compiled = compilePrompt();
                                            setSystemPrompt(compiled);
                                            handleSaveConfig();
                                        }}
                                        disabled={savingConfig}
                                    >
                                        {savingConfig ? <CircularProgress size={24} /> : 'Sync & Save AI Behavior'}
                                    </Button>
                                </Box>
                            </Box>
                        </Paper>
                    ) : (
                        <Paper sx={{ p: 4, elevation: 3 }}>
                            <Typography variant="h6" gutterBottom>Master System Prompt Control</Typography>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                                ⚠️ Caution: Editing this template can break AI parsing logic. Use placeholders like {"{history_text}"} carefully.
                            </Typography>
                            <TextField
                                fullWidth
                                multiline
                                rows={15}
                                value={systemPrompt}
                                onChange={(e) => setSystemPrompt(e.target.value)}
                                sx={{
                                    mb: 3,
                                    '& .MuiInputBase-input': { fontFamily: 'monospace', fontSize: '0.85rem' }
                                }}
                            />
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Button
                                    color="error"
                                    onClick={handleResetConfig}
                                    disabled={resetting}
                                >
                                    {resetting ? <CircularProgress size={20} /> : 'Restore Defaults'}
                                </Button>
                                <Box sx={{ display: 'flex', gap: 2 }}>
                                    <Button onClick={fetchSystemConfig}>Discard Changes</Button>
                                    <Button variant="contained" onClick={handleSaveConfig} disabled={savingConfig}>
                                        Save Raw Prompt
                                    </Button>
                                </Box>
                            </Box>
                        </Paper>
                    )}
                </Box>
            )}

            {/* User Role Dialog */}
            <Dialog open={userDialog} onClose={() => setUserDialog(false)}>
                <DialogTitle>Edit User Role: {currentUser.name}</DialogTitle>
                <DialogContent sx={{ minWidth: 400, pt: 2 }}>
                    <FormControl fullWidth sx={{ mb: 2, mt: 1 }}>
                        <InputLabel>Display Role Name</InputLabel>
                        <Select
                            value={currentUser.role}
                            label="Display Role Name"
                            onChange={(e) => setCurrentUser({ ...currentUser, role: e.target.value })}
                        >
                            <MenuItem value="Analyst">Analyst</MenuItem>
                            <MenuItem value="Manager">Manager</MenuItem>
                            <MenuItem value="admin">Administrator</MenuItem>
                        </Select>
                    </FormControl>

                    <FormControl fullWidth>
                        <InputLabel>Security Policy</InputLabel>
                        <Select
                            value={currentUser.rolePolicy}
                            label="Security Policy"
                            onChange={(e) => setCurrentUser({ ...currentUser, rolePolicy: e.target.value })}
                        >
                            <MenuItem value=""><em>None (Public Access)</em></MenuItem>
                            {policies.map(p => (
                                <MenuItem key={p._id} value={p._id}>{p.name}</MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setUserDialog(false)}>Cancel</Button>
                    <Button onClick={handleSaveUserRole} variant="contained">Update User</Button>
                </DialogActions>
            </Dialog>

            {/* Policy Editor Dialog */}
            <Dialog open={policyDialog} onClose={() => setPolicyDialog(false)} fullWidth maxWidth="md">
                <DialogTitle>{currentPolicy._id ? 'Edit Role Policy' : 'Create Role Policy'}</DialogTitle>
                <DialogContent>
                    <TextField
                        fullWidth
                        label="Role Name"
                        value={currentPolicy.name}
                        onChange={(e) => setCurrentPolicy({ ...currentPolicy, name: e.target.value })}
                        sx={{ mt: 2, mb: 2 }}
                    />
                    <TextField
                        fullWidth
                        multiline
                        rows={2}
                        label="Description"
                        value={currentPolicy.description}
                        onChange={(e) => setCurrentPolicy({ ...currentPolicy, description: e.target.value })}
                        sx={{ mb: 2 }}
                    />
                    <Typography variant="subtitle2" gutterBottom sx={{ mt: 3 }}>Data Permission Matrix</Typography>
                    <Box sx={{ mb: 3 }}>
                        {currentPolicy.permissions.collections.map((coll, idx) => (
                            <Paper key={idx} variant="outlined" sx={{ p: 2, mb: 2, backgroundColor: 'rgba(0,0,0,0.02)' }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                    <Typography variant="subtitle1" fontWeight="bold">{coll.database}.{coll.name}</Typography>
                                    <Button
                                        size="small"
                                        color="error"
                                        onClick={() => {
                                            const newColls = currentPolicy.permissions.collections.filter((_, i) => i !== idx);
                                            setCurrentPolicy({ ...currentPolicy, permissions: { ...currentPolicy.permissions, collections: newColls } });
                                        }}
                                    >
                                        Remove
                                    </Button>
                                </Box>
                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                    {['find', 'aggregate', 'insert', 'update', 'delete'].map(op => (
                                        <Chip
                                            key={op}
                                            label={op.toUpperCase()}
                                            onClick={() => {
                                                const ops = coll.operations.includes(op)
                                                    ? coll.operations.filter(o => o !== op)
                                                    : [...coll.operations, op];
                                                const newColls = [...currentPolicy.permissions.collections];
                                                newColls[idx] = { ...coll, operations: ops };
                                                setCurrentPolicy({ ...currentPolicy, permissions: { ...currentPolicy.permissions, collections: newColls } });
                                            }}
                                            color={coll.operations.includes(op) ? "primary" : "default"}
                                            variant={coll.operations.includes(op) ? "filled" : "outlined"}
                                            size="small"
                                        />
                                    ))}
                                </Box>
                            </Paper>
                        ))}
                    </Box>
                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                        <FormControl size="small" sx={{ minWidth: 200 }}>
                            <InputLabel>Select Collection</InputLabel>
                            <Select
                                label="Select Collection"
                                value=""
                                onChange={(e) => {
                                    if (!e.target.value) return;
                                    const newColl = { database: '*', name: e.target.value, operations: ['find'], fields: ['*'], restrictedFields: [] };
                                    setCurrentPolicy({ ...currentPolicy, permissions: { ...currentPolicy.permissions, collections: [...currentPolicy.permissions.collections, newColl] } });
                                }}
                            >
                                <MenuItem value="*"><em>All Collections (*)</em></MenuItem>
                                {fetchedCollections.map(c => (
                                    <MenuItem key={c} value={c}>{c}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                        <Typography variant="caption" color="text.secondary">
                            Pick a collection to add specific permissions
                        </Typography>
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setPolicyDialog(false)}>Cancel</Button>
                    <Button onClick={handleSavePolicy} variant="contained">Save Policy</Button>
                </DialogActions>
            </Dialog>

            <Snackbar
                open={snackbar.open}
                autoHideDuration={6000}
                onClose={() => setSnackbar({ ...snackbar, open: false })}
            >
                <Alert severity={snackbar.severity} sx={{ width: '100%' }}>
                    {snackbar.message}
                </Alert>
            </Snackbar>
        </Box>
    );
};

export default AdminPortal;
