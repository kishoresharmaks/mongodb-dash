import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    AppBar,
    Toolbar,
    Typography,
    IconButton,
    Menu,
    MenuItem,
    Box,
    Switch,
    FormControlLabel,
    Tooltip
} from '@mui/material';
import AccountCircle from '@mui/icons-material/AccountCircle';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import HistoryIcon from '@mui/icons-material/History';

const Navbar = ({ darkMode, toggleDarkMode, onToggleHistory }) => {
    const navigate = useNavigate();
    const [anchorEl, setAnchorEl] = useState(null);

    const user = JSON.parse(localStorage.getItem('user') || '{}');

    const handleMenu = (event) => {
        setAnchorEl(event.currentTarget);
    };

    const handleClose = () => {
        setAnchorEl(null);
    };

    const handleLogout = () => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        navigate('/login');
    };

    return (
        <AppBar position="static">
            <Toolbar>
                <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                    NLP MongoDB Interface
                </Typography>

                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Tooltip title="History">
                        <IconButton color="inherit" onClick={onToggleHistory}>
                            <HistoryIcon />
                        </IconButton>
                    </Tooltip>

                    <IconButton color="inherit" onClick={toggleDarkMode}>
                        {darkMode ? <Brightness7Icon /> : <Brightness4Icon />}
                    </IconButton>

                    <Typography variant="body2" sx={{ mr: 1 }}>
                        {user.name || 'User'}
                    </Typography>

                    <IconButton
                        size="large"
                        onClick={handleMenu}
                        color="inherit"
                    >
                        <AccountCircle />
                    </IconButton>

                    <Menu
                        anchorEl={anchorEl}
                        open={Boolean(anchorEl)}
                        onClose={handleClose}
                    >
                        <MenuItem onClick={handleClose}>
                            <Typography variant="body2">{user.email}</Typography>
                        </MenuItem>
                        {user.role === 'admin' && (
                            <MenuItem onClick={() => { handleClose(); navigate('/admin'); }}>
                                Admin Portal
                            </MenuItem>
                        )}
                        <MenuItem onClick={handleLogout}>Logout</MenuItem>
                    </Menu>
                </Box>
            </Toolbar>
        </AppBar>
    );
};

export default Navbar;
