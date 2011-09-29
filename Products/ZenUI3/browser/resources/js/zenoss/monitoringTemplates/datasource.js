/*
###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2010, Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################
*/

(function(){

var router, dataSourcesId, graphsId, resetCombo,
    addMetricToGraph, showAddToGraphDialog, editDataSourcesId, treeId,
    dataSourceMenu, editingReSelectId;

Ext.ns('Zenoss');

router = Zenoss.remote.TemplateRouter;
dataSourcesId = 'dataSourceTreeGrid';
graphsId = 'graphGrid';
editDataSourcesId = "editDataSource";

// NOTE: this must match the tree id from the template.js file
treeId = 'templateTree';

/**
 *@returns the currently selected Data Source or Data Point, or none if nothing is selected
 **/
function getSelectedDataSourceOrPoint() {
    return Ext.getCmp(dataSourcesId).getSelectionModel().getSelectedNode();
}

resetCombo = function(combo, uid) {
    combo.clearValue();
    combo.getStore().setBaseParam('uid', uid);
    delete combo.lastQuery;
    combo.doQuery(combo.allQuery, true);
};

addMetricToGraph = function(dataPointUid, graphUid) {
    var params, callback;
    params = {dataPointUid: dataPointUid, graphUid: graphUid};
    callback = function(provider, response) {
        Ext.getCmp(graphsId).getStore().reload();
    };
    router.addDataPointToGraph(params, callback);
};

Ext.define('Zenoss.GraphModel', {
    extend: 'Ext.data.Model',
    idProperty: 'uid',
    fields: [
        'uid', 'name', 'graphPoints', 'units', 'height', 'width',
             'sequence'
    ]
});

Ext.define("Zenoss.GraphStore", {
    extend:"Zenoss.NonPaginatedStore",
    alias: ['widget.graphstore'],
    constructor: function(config) {
        Ext.applyIf(config, {
            root: 'data',
            directFn: router.getGraphs,
            model: 'Zenoss.GraphModel'
        });
        this.callParent(arguments);
    }
});


new Zenoss.HideFormDialog({
    id: 'addToGraphDialog',
    width: 400,
    height: 150,
    title: _t('Add Data Point to Graph'),
    items: [
    {
        xtype: 'panel',
        id: 'addToGraphMetricPanel',
        border: false
    }, {
        xtype: 'combo',
        id: 'graphCombo',
        fieldLabel: _t('Graph'),
        displayField: 'name',
        valueField: 'uid',
        forceSelection: true,
        width:300,
        minChars: 999, // only do an all query
        triggerAction: 'all',
        resizeable: true,
        emptyText: 'Select a graph...',
        selectOnFocus: true,
        store: new Zenoss.GraphStore({}),
        listeners: {select: function(){
            Ext.getCmp('addToGraphDialog').submit.enable();
        }}
    }],
    buttons: [
    {
        xtype: 'HideDialogButton',
        ref: '../submit',
        text: _t('Submit'),
        disabled: true,
        handler: function(button, event) {
            var node, datapointUid, graphUid;
            node = Ext.getCmp(dataSourcesId).getSelectionModel().getSelectedNode();
            datapointUid = node.data.uid;
            graphUid = Ext.getCmp('graphCombo').getValue();
            addMetricToGraph(datapointUid, graphUid);
        }
    }, {
        xtype: 'HideDialogButton',
        text: _t('Cancel')
    }]
});

showAddToGraphDialog = function() {
    var smTemplate, templateUid, smDataSource,
        nodeDataSource, metricName, html, combo;
    smTemplate = Ext.getCmp('templateTree').getSelectionModel();
    templateUid = smTemplate.getSelectedNode().data.uid;
    smDataSource = Ext.getCmp(dataSourcesId).getSelectionModel();
    nodeDataSource = smDataSource.getSelectedNode();
    if ( nodeDataSource && nodeDataSource.isLeaf() ) {
        metricName = nodeDataSource.data.name;
        html = '<div>Data Point</div>';
        html += '<div>' + metricName + '</div><br/>';
        Ext.getCmp('addToGraphDialog').show();
        Ext.getCmp('addToGraphMetricPanel').body.update(html);
        combo = Ext.getCmp('graphCombo');
        resetCombo(combo, templateUid);
        Ext.getCmp('addToGraphDialog').submit.disable();
    } else {
        Ext.Msg.alert('Error', 'You must select a Data Point.');
    }
};


/**********************************************************************
 *
 * Add Data Point
 *
 **/

/**
 * Causes the DataSources Grid to refresh from the server
 *
 **/
function refreshDataSourceGrid(selectedId) {
    var grid = Ext.getCmp(dataSourcesId);
    Ext.getCmp('addDataPointDialog').hide();
    Ext.getCmp('addDataSourceDialog').hide();
    if (selectedId) {
        grid.refresh(function(){
            grid.getRootNode().cascade(function(node){
                if (node.data.id == selectedId) {
                    node.expand();
                    node.select();
                }
            });
        });
    }else{
        grid.refresh();
    }
}

/**
 * Gets the DataPoint name from the dialog and sends it to the server
 **/
function saveDataPoint() {
    var grid = Ext.getCmp(dataSourcesId),
        selectedNode = grid.getSelectionModel().getSelectedNode(),
        parameters, selectedId;

    // if we have a datapoint, find the datasource associated with it
    if (selectedNode.data.leaf) {
        selectedNode = selectedNode.parentNode;
    }

    parameters = {
        name: Ext.getCmp('metricName').getValue(),
        dataSourceUid: selectedNode.data.uid
    };
    selectedId = selectedNode.data.id;
    // get selected datasource, and reopen the grid to that point
    function callback() {
        refreshDataSourceGrid(selectedId);
    }
    return router.addDataPoint(parameters, callback);

}

/**
 * Add Data Point Dialog Configuration
 **/
new Zenoss.dialog.BaseWindow({
        id: 'addDataPointDialog',
        title: _t('Add Data Point'),
        height: 160,
        width: 310,
        plain: true,
        modal: true,

        closeAction: 'hide',
        listeners: {
            hide: function() {
                Ext.getCmp('metricName').setValue(null);
                Ext.getCmp('metricName').clearInvalid();
            }
        },
        items:{
            xtype: 'form',
            border: false,
            buttonAlign: 'left',
            monitorValid: true,
            items: [{
                xtype: 'idfield',
                id: 'metricName',
                fieldLabel: _t('Name'),
                allowBlank: false,
                blankText: _t('Name is a required field')
                   }],
            buttons: [{
                    xtype: 'button',
                    text: _t('Submit'),
                    formBind: true,
                    handler: saveDataPoint
                }, {
                    xtype: 'button',
                    text: _t('Cancel'),
                    handler: function() {
                        Ext.getCmp('addDataPointDialog').hide();
                    }
                }]

        }

    }
);

/**
 * Displays the Add Data Point dialog and saves the inputted infomation
 * back to the server
 **/
function showAddDataPointDialog() {
    var grid = Ext.getCmp(dataSourcesId),
        selectedNode = grid.getSelectionModel().getSelectedNode();

    // make sure they selected a node
    if (!selectedNode) {
        Ext.Msg.alert(_t('Error'), _t('You must select data source'));
        return;
    }

    // display the name dialog
    Ext.getCmp('addDataPointDialog').show();
}

/**********************************************************************
 *
 * Add Data Source
 *
 */

/**
 * Gets the info from the Add Datasource dialog and sends it to the server
 **/
function saveDataSource() {
    var grid = Ext.getCmp(treeId),
        selectedNode = grid.getSelectionModel().getSelectedNode(),
        parameters = {
            name: Ext.getCmp('dataSourceName').getValue(),
            type: Ext.getCmp('dataSourceTypeCombo').getValue(),
            templateUid: selectedNode.data.uid
        };
    return router.addDataSource(parameters, refreshDataSourceGrid);
}

new Zenoss.dialog.BaseWindow({
        id: 'addDataSourceDialog',
        title: _t('Add Data Source'),
        height: 180,
        width: 350,
        modal: true,
        plain: true,
        closeAction: 'hide',
        buttonAlight: 'left',
        listeners: {
            hide: function() {
                Ext.getCmp('dataSourceTypeCombo').setValue('SNMP');
                Ext.getCmp('dataSourceName').setValue('');
                Ext.getCmp('dataSourceName').clearInvalid();
            }
        },
        items:{
            xtype:'form',
            border: false,
            buttonAlign: 'left',
            monitorValid: true,
            items:[{
            xtype: 'idfield',
            id: 'dataSourceName',
            fieldLabel: _t('Name'),
            allowBlank: false,
            blankText: _t('Name is a required field')
          },
          {
            xtype: 'combo',
            id: 'dataSourceTypeCombo',
            displayField: 'type',
            fieldLabel: _t('Type'),
            editable: false,
            forceSelection: true,
            autoSelect: true,
            value: 'SNMP',
            selectOnFocus: true,
            triggerAction: 'all',
            store:  {
                type: 'directcombo',
                fields: ['type'],
                root: 'data',
                directFn: router.getDataSourceTypes
            }
        }],
        buttons:[{
            xtype: 'button',
            text: _t('Submit'),
            formBind: true,
            handler: saveDataSource
        },{
            xtype: 'button',
            text: _t('Cancel'),
            handler: function () {
                Ext.getCmp('addDataSourceDialog').hide();
            }
        }]}
});

/**
 * Shows the Add Data Source dialog and saves the inputted information
 * back to the server
 **/
function showAddDataSourceDialog() {
    var cmp = Ext.getCmp(treeId),
        selectedNode = cmp.getSelectionModel().getSelectedNode();

    // make sure they selected a node
    if (!selectedNode) {
        Ext.Msg.alert(_t('Error'), _t('You must select a template'));
        return;
    }
    // clear the entries (all of our forms are blank when you load them)
    Ext.getCmp('addDataSourceDialog').show();
}

/**********************************************************************
 *
 * Delete DataSource
 *
 */

/**
 * Creates the dynamic delete message and shows the dialog
 **/
function showDeleteDataSourceDialog() {
    var msg, name, html, dialog;
    if (getSelectedDataSourceOrPoint()) {
        // set up the custom delete message
        msg = _t("Are you sure you want to remove {0}? There is no undo.");
        name = getSelectedDataSourceOrPoint().data.name;
        html = String.format(msg, name);

        // show the dialog
        dialog = Ext.getCmp('deleteDataSourceDialog');
        dialog.show();
        dialog.getComponent('message').update(html);
    }else{
        Ext.Msg.alert(_t('Error'), _t('You must select a Data Source or Data Point.'));
    }
}

new Zenoss.MessageDialog({
    id: 'deleteDataSourceDialog',
    title: _t('Delete'),
    // msg is generated dynamically
    okHandler: function(){
        var params, node = getSelectedDataSourceOrPoint(),
        selectedId;
        params = {
            uid: getSelectedDataSourceOrPoint().get("uid")
        };

        // data points are always leafs
        if (getSelectedDataSourceOrPoint().data.leaf) {
            selectedId = node.parentNode.data.id;
            function callback() {
                refreshDataSourceGrid(selectedId);
            }
            router.deleteDataPoint(params, callback);
        }else {
            router.deleteDataSource(params, refreshDataSourceGrid);
        }
    }
});

/**********************************************************************
 *
 * Edit DataSource/DataPoint
 *
 */

/**
 * Closes the edit dialog and updates the store of the datasources.
 * This is called after the router request to save the edit dialog
 **/
function closeEditDialog(response) {
    var dialog = Ext.getCmp('editDataSources');
    refreshDataSourceGrid(editingReSelectId);

    // hide the dialog
    if (dialog) {
        dialog.hide();
    }
}

/**
 * Event handler for when a user wants to test a datasource
 * against a specific device.
 **/
function testDataSource() {
    var cmp = Ext.getCmp(editDataSourcesId),
        values = cmp.editForm.form.getValues(),
        win, testDevice, data;

    testDevice = values.testDevice;

    win = new Zenoss.CommandWindow({
        uids: testDevice,
        title: _t('Test Data Source'),
        data: values,
        target: values.uid + '/test_datasource'
    });

    win.show();
}

/**
 * Used when we save the data grid, it needs to
 * explicitly get the "Alias" value and turn it into a
 * list before going back to the server
 **/
function submitDataPointForm (values, callback) {
    // will always have only one alias form
    var aliases = Ext.getCmp(editDataSourcesId).query('alias'),
        alias;
    // assert that we have one exactly one alias form
    if (aliases.length < 1) {
        throw "The DataPoint form does not have an alias field, it should have only one";
    }

    alias = aliases[0];
    values.aliases = alias.getValue();
    router.setInfo(values, callback);
}

/**
 * Event handler for editing a specific datasource or
 * datapoint.
 **/
function editDataSourceOrPoint() {
    var cmp = Ext.getCmp(dataSourcesId),
        selectedNode = cmp.getSelectionModel().getSelectedNode(),
        data,
        isDataPoint = false,
        params, reselectId;

    // make sure they selected something
    if (!selectedNode) {
        Ext.Msg.alert(_t('Error'), _t('You must select a data source or data point.'));
        return;
    }
    data = selectedNode.data;

    // find out if we are editing a datasource or a datapoint
    if (data.leaf) {
        isDataPoint = true;
        editingReSelectId = selectedNode.parentNode.data.id;
    }else{
        editingReSelectId = data.id;
    }

    // parameters for the router call
    params = {
        uid: data.uid
    };

    // callback for the router request
    function displayEditDialog(response) {
        var win,
        config = {};

        config.record = response.record;
        config.items = response.form;
        config.id = editDataSourcesId;
        config.isDataPoint = isDataPoint;
        config.title = _t('Edit Data Source');
        config.directFn = router.setInfo;
        config.width = 800;
        if (isDataPoint) {
            config.title = _t('Edit Data Point');
            config.directFn = submitDataPointForm;
            config.singleColumn = true;
        }else if (config.record.testable &&
                  Zenoss.Security.hasPermission('Change Device')){
            // add the test against device panel
            config.items.items.push({
                xtype:'panel',
                columnWidth: 0.5,
                baseCls: 'test-against-device',
                hidden: Zenoss.Security.doesNotHavePermission('Run Commands'),
                title: _t('Test Against a Device'),
                items:[{
                    xtype: 'textfield',
                    fieldLabel: _t('Device Name'),
                    id: 'testDevice',
                    name: 'testDevice'
                },{
                    xtype: 'hidden',
                    name: 'uid',
                    value: response.record.id
                },{
                    xtype: 'button',
                    text: _t('Test'),
                    handler: testDataSource
                }]});

        }

        config.saveHandler = closeEditDialog;
        win = new Zenoss.form.DataSourceEditDialog(config);
        win.show();
    }
    // get the details
    if (isDataPoint) {
        router.getDataPointDetails(params, displayEditDialog);
    }else{
        router.getDataSourceDetails(params, displayEditDialog);
    }
}

dataSourceMenu = new Ext.menu.Menu({
    id: 'dataSourceMenu',
    items: [{
        xtype: 'menuitem',
        text: _t('Add Data Point To Graph'),
        disable: Zenoss.Security.doesNotHavePermission('Manage DMD'),
        handler: showAddToGraphDialog
    },{
        xtype: 'menuitem',
        text: _t('Add Data Point'),
        disable: Zenoss.Security.doesNotHavePermission('Manage DMD'),
        handler: showAddDataPointDialog
    },{
        xtype: 'menuitem',
        text: _t('View and Edit Details'),
        disable: Zenoss.Security.doesNotHavePermission('Manage DMD'),
        handler: editDataSourceOrPoint
    }]
});


/**
 * @class Zenoss.templates.DataSourceModel
 * @extends Ext.data.Model
 * Field definitions for the datasource/datapoint grid
 **/
Ext.define('Zenoss.templates.DataSourceModel',  {
    extend: 'Ext.data.Model',
    idProperty: 'uid',
    fields: [
        {name: 'uid'},
        {name: 'name'},
        {name: 'source'},
        {name: 'enabled'},
        {name: 'type'}
    ]
});

/**
 * @class Zenoss.templates.DataSourceStore
 * @extend Ext.data.TreeStore
 * Direct store for loading datasources and datapoints
 */
Ext.define("Zenoss.templates.DataSourceStore", {
    extend: "Ext.data.TreeStore",
    constructor: function(config) {
        config = config || {};
        Ext.applyIf(config, {
            model: 'Zenoss.templates.DataSourceModel',
            nodeParam: 'uid',
            remoteSort: false,
            proxy: {
                type: 'direct',
                directFn: router.getDataSources,
                reader: {
                    root: 'data',
                    totalProperty: 'count'
                }
            }
        });
        this.callParent(arguments);
    }
});

/**
 * @class Zenoss.DataSourceTreeGrid
 * @extends Ext.Tree.Panel
 * @constructor
 */
Ext.define("Zenoss.DataSourceTreeGrid", {
    extend: "Ext.tree.Panel",
    alias: ['widget.DataSourceTreeGrid'],

    constructor: function(config) {
        Ext.applyIf(config, {
            border: false,
            useArrows: true,
            cls: 'x-tree-noicon',
            rootVisible: false,
            id: dataSourcesId,
            title: _t('Data Sources'),
            listeners: {
                // when they doubleclick we will open up the tree and
                // display the dialog
                beforeitemdblclick: editDataSourceOrPoint
            },
            store: Ext.create('Zenoss.templates.DataSourceStore', {}),
            tbar: [{
                    xtype: 'button',
                    iconCls: 'add',
                    id:'datasourceAddButton',
                    ref: '../addButton',
                    disabled: Zenoss.Security.doesNotHavePermission('Manage DMD'),
                    handler: showAddDataSourceDialog,
                    listeners: {
                        render: function() {
                            Zenoss.registerTooltipFor('datasourceAddButton');
                        }
                    }
            }, {
                xtype: 'button',
                iconCls: 'delete',
                ref: '../deleteButton',
                id: 'datasourceDeleteButton',
                disabled: Zenoss.Security.doesNotHavePermission('Manage DMD'),
                listeners: {
                    render: function() {
                        Zenoss.registerTooltipFor('datasourceDeleteButton');
                    }
                },
                handler: showDeleteDataSourceDialog
            },{
                xtype: 'button',
                id: 'datasourceEditButton',
                iconCls: 'customize',
                ref: '../customizeButton',
                disabled: Zenoss.Security.doesNotHavePermission('Manage DMD'),
                listeners: {
                    render: function() {
                        Zenoss.registerTooltipFor('datasourceEditButton');
                    }
                },
                menu: 'dataSourceMenu'
            }],
            columns: [{
                xtype: 'treecolumn', //this is so we know which column will show the tree
                text: 'Name',
                flex: 2,
                sortable: true,
                dataIndex: 'name'
            }, {
                dataIndex: 'source',
                flex: 1,
                header: 'Source',
                width: 250
            }, {
                dataIndex: 'enabled',
                header: 'Enabled',
                width: 40
            }, {
                dataIndex: 'type',
                header: 'Type',
                width: 90
            }],
            selModel: Ext.create('Zenoss.TreeSelectionModel', {
                mode: 'SINGLE'
            })
        });
        this.callParent(arguments);
    },
    disableToolBarButtons: function(bool) {
        this.addButton.setDisabled(bool && Zenoss.Security.hasPermission('Manage DMD'));
        this.deleteButton.setDisabled(bool && Zenoss.Security.hasPermission('Manage DMD'));
        this.customizeButton.setDisabled(bool && Zenoss.Security.hasPermission('Manage DMD'));
    },
    setContext: function(uid) {
        this.uid = uid;
        this.refresh();
    },
    refresh: function(callback, scope) {
        var root = this.getRootNode();
        root.setId(this.uid);
        root.data.uid = this.uid;
        root.uid = this.uid;
        if (callback) {
            this.getStore().load({
                callback: callback,
                scope: scope || this
            });
        }else {
            this.getStore().load();
        }

    }

});



})();
