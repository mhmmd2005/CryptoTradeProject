# from django.test import TestCase
#
# # Create your tests here.
# <!doctype html>
# <html lang="en" data-layout="vertical" data-topbar="light" data-sidebar="light" data-sidebar-size="lg"
#       data-sidebar-image="none">
#
#
# <!-- Mirrored from themesbrand.com/velzon/html/minimal/tables-listjs.html by HTTrack Website Copier/3.x [XR&CO'2014], Thu, 16 Jun 2022 09:47:20 GMT -->
# <head>
#
#     <meta charset="utf-8"/>
#     <title>User List</title>
#     <meta name="viewport" content="width=device-width, initial-scale=1.0">
#     <meta content="Premium Multipurpose Admin & Dashboard Template" name="description"/>
#     <meta content="Themesbrand" name="author"/>
#     <!-- App favicon -->
#     <link rel="shortcut icon" href="/static/assets/images/favicon.ico">
#
#     <!-- Sweet Alert css-->
#     <link href="/static/assets/libs/sweetalert2/sweetalert2.min.css" rel="stylesheet" type="text/css"/>
#
#     <!-- Layout config Js -->
#     <script src="/static/assets/js/layout.js"></script>
#     <!-- Bootstrap Css -->
#     <link href="/static/assets/css/bootstrap.min.css" rel="stylesheet" type="text/css"/>
#     <!-- Icons Css -->
#     <link href="/static/assets/css/icons.min.css" rel="stylesheet" type="text/css"/>
#     <!-- App Css-->
#     <link href="/static/assets/css/app.min.css" rel="stylesheet" type="text/css"/>
#     <!-- custom Css-->
#     <link href="/static/assets/css/custom.min.css" rel="stylesheet" type="text/css"/>
#     <!-- Material Symbols Outlined -->
#     <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet"/>
#     <style>
#         .delete-button {
#             position: relative;
#             padding: 0.25em; /* کمی کمتر */
#             border: none;
#             background: transparent;
#             cursor: pointer;
#             font-size: 0.85em; /* کمی کمتر */
#             transition: transform 0.2s ease;
#             top: -4px; /* کمی کمتر به بالا */
#             left: 5px; /* کمی کمتر به راست */
#         }
#
#         .trash-svg {
#             width: 2.2em; /* کمی کمتر */
#             height: 2.2em; /* کمی کمتر */
#             transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
#             filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
#             overflow: visible;
#         }
#
#         #lid-group {
#             transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
#         }
#
#         .delete-button:hover #lid-group {
#             transform: rotate(-28deg) translateY(1px);
#         }
#
#         .delete-button:active #lid-group {
#             transform: rotate(-12deg) scale(0.98);
#         }
#
#         .delete-button:hover .trash-svg {
#             transform: scale(1.05) rotate(3deg); /* کمی کمتر بزرگ شود */
#         }
#
#         .delete-button:active .trash-svg {
#             transform: scale(0.95) rotate(-1deg);
#         }
#
#         .empty-row td {
#             text-align: center;
#         {#padding-right: 15px; /* اختیاری برای فاصله از لبه */#}
#         }
#
#     </style>
#
# </head>
#
# <body>
#
# <!-- Begin page -->
# <div id="layout-wrapper">
#
#     {% include 'header_include/header_include.html' %}
#     <!-- ========== App Menu ========== -->
#     <div class="app-menu navbar-menu">
#         <!-- LOGO -->
#         <div class="navbar-brand-box">
#             <!-- Dark Logo-->
#             <a href="index.html" class="logo logo-dark">
#                     <span class="logo-sm">
#                         <img src="/static/assets/images/logo-sm.png" alt="" height="22">
#                     </span>
#                 <span class="logo-lg">
#                         <img src="/static/assets/images/logo-dark.png" alt="" height="17">
#                     </span>
#             </a>
#             <!-- Light Logo-->
#             <a href="index.html" class="logo logo-light">
#                     <span class="logo-sm">
#                         <img src="/static/assets/images/logo-sm.png" alt="" height="22">
#                     </span>
#                 <span class="logo-lg">
#                         <img src="/static/assets/images/logo-light.png" alt="" height="17">
#                     </span>
#             </a>
#             <button type="button" class="btn btn-sm p-0 fs-20 header-item float-end btn-vertical-sm-hover"
#                     id="vertical-hover">
#                 <i class="ri-record-circle-line"></i>
#             </button>
#         </div>
#
#         {% include 'sidebar_include/sidebar_include.html' %}
#     </div>
#     <!-- Left Sidebar End -->
#     <!-- Vertical Overlay-->
#     <div class="vertical-overlay"></div>
#
#     <!-- ============================================================== -->
#     <!-- Start right Content here -->
#     <!-- ============================================================== -->
#     <div class="main-content">
#
#         <div class="page-content">
#             <div class="container-fluid">
#
#                 <!-- start page title -->
#                 <div class="row">
#                     <div class="col-12">
#                         <div class="page-title-box d-sm-flex align-items-center justify-content-between">
#                             <h4 class="mb-sm-0">User List</h4>
#
#                             <div class="page-title-right">
#                                 <ol class="breadcrumb m-0">
#                                     <li class="breadcrumb-item"><a href="javascript: void(0);">Tables</a></li>
#                                     <li class="breadcrumb-item active">User List</li>
#                                 </ol>
#                             </div>
#
#                         </div>
#                     </div>
#                 </div>
#                 <!-- end page title -->
#
#                 <div class="row">
#                     <div class="col-lg-12">
#                         <div class="card">
#                             <div class="card-header">
#                                 <h4 class="card-title mb-0">User Table</h4>
#                             </div><!-- end card header -->
#
#                             <div class="card-body">
#                                 <div id="customerList">
#                                     <div class="row g-4 mb-3">
#                                         <div class="col-sm-auto">
#                                             <button class="btn btn-soft-danger" onclick="deleteMultiple()"><i
#                                                     class="ri-delete-bin-2-line"></i></button>
#                                         </div>
#                                         <div class="col-sm">
#                                             <div class="d-flex justify-content-sm-end">
#                                                 <div class="input-group ms-2" style="max-width: 300px;">
#                                                     <input type="text" id="searchInput" class="form-control"
#                                                            placeholder="Search...">
#                                                     <span class="input-group-text bg-primary text-white"
#                                                           style="cursor:pointer;">
#                 <i class="ri-search-line"></i>
#             </span>
#                                                 </div>
#                                             </div>
#                                         </div>
#
#                                     </div>
#
#                                     <div class="table-responsive table-card mt-3 mb-1">
#                                         <table class="table align-middle table-nowrap" id="customerTable">
#                                             <thead class="table-light">
#                                             <tr>
#                                                 <th scope="col" style="width: 50px;">
#                                                     <div class="form-check">
#                                                         <input class="form-check-input" type="checkbox" id="checkAll"
#                                                                value="option">
#                                                     </div>
#                                                 </th>
#                                                 <th class="sort" data-sort="customer_name">Customer</th>
#                                                 <th class="sort" data-sort="email">Email</th>
#                                                 <th class="sort" data-sort="phone">Phone</th>
#                                                 <th class="sort" data-sort="date">Country</th>
#                                                 <th class="sort" data-sort="status">Delivery Status</th>
#                                                 <th class="sort" data-sort="action">Action</th>
#                                             </tr>
#                                             </thead>
#                                             <tbody class="list form-check-all">
#                                             {% for item in page_obj %}
#                                                 <tr>
#                                                     <th scope="row">
#                                                         <div class="form-check">
#                                                             <input class="form-check-input checkItem" type="checkbox"
#                                                                    name="chk_child" value="{{ item.profile.id }}">
#                                                         </div>
#                                                     </th>
#                                                     <td class="customer_name">{{ item.profile.first_name }} {{ item.profile.last_name }}</td>
#                                                     <td class="email">{{ item.profile.user.email }}</td>
#                                                     <td class="phone">{{ item.profile.phone_number }}</td>
#                                                     <td class="date">{{ item.profile.country }}</td>
#                                                     <td class="status">
#                                                         {% if item.status == 'pending' %}
#                                                             <span class="badge badge-soft-warning text-uppercase">Pending</span>
#                                                         {% elif item.status == 'approved' %}
#                                                             <span class="badge badge-soft-success text-uppercase">Approved</span>
#                                                         {% elif item.status == 'rejected' %}
#                                                             <span class="badge badge-soft-danger text-uppercase">Rejected</span>
#                                                         {% else %}
#                                                             <span class="badge badge-soft-secondary text-uppercase">{{ item.status }}</span>
#                                                         {% endif %}
#                                                     </td>
#                                                     <td>
#                                                         <div class="d-flex gap-2 align-items-center">
#                                                             <!-- آیکون چشم به جای Edit -->
#                                                             <a href="{% url 'dashboard:profile_detail' pk=item.profile.pk %}"
#                                                                target="_blank" title="View">
#     <span class="material-symbols-outlined"
#           style="font-size: 20px; cursor: pointer;">visibility</span>
#                                                             </a>
#
#                                                             <!-- دکمه Remove -->
#                                                             <!-- From Uiverse.io by philipo30 -->
#                                                             <button aria-label="Delete item" class="delete-button"
#                                                                     data-id="{{ item.profile.id }}">
#                                                                 <svg
#                                                                         class="trash-svg"
#                                                                         viewBox="0 -10 64 74"
#                                                                         xmlns="http://www.w3.org/2000/svg"
#                                                                 >
#                                                                     <g id="trash-can">
#                                                                         <rect
#                                                                                 x="16"
#                                                                                 y="24"
#                                                                                 width="32"
#                                                                                 height="30"
#                                                                                 rx="3"
#                                                                                 ry="3"
#                                                                                 fill="#e74c3c"
#                                                                         ></rect>
#
#                                                                         <g transform-origin="12 18" id="lid-group">
#                                                                             <rect
#                                                                                     x="12"
#                                                                                     y="12"
#                                                                                     width="40"
#                                                                                     height="6"
#                                                                                     rx="2"
#                                                                                     ry="2"
#                                                                                     fill="#c0392b"
#                                                                             ></rect>
#                                                                             <rect
#                                                                                     x="26"
#                                                                                     y="8"
#                                                                                     width="12"
#                                                                                     height="4"
#                                                                                     rx="2"
#                                                                                     ry="2"
#                                                                                     fill="#c0392b"
#                                                                             ></rect>
#                                                                         </g>
#                                                                     </g>
#                                                                 </svg>
#                                                             </button>
#                                                         </div>
#                                                     </td>
#                                                 </tr>
#                                             {% endfor %}
#                                             </tbody>
#                                         </table>
#                                         <div class="noresult" style="display: none">
#                                             <div class="text-center">
#                                                 <lord-icon src="https://cdn.lordicon.com/msoeawqm.json" trigger="loop"
#                                                            colors="primary:#25a0e2,secondary:#00bd9d"
#                                                            style="width:75px;height:75px">
#                                                 </lord-icon>
#                                                 <h5 class="mt-2">Sorry! No Result Found</h5>
#                                                 <p class="text-muted mb-0">We've searched more than 150+ Orders We did
#                                                     not find any
#                                                     orders for you search.</p>
#                                             </div>
#                                         </div>
#                                     </div>
#
#                                     <div class="d-flex justify-content-end">
#                                         <div class="pagination-wrap hstack gap-2">
#                                             {% if page_obj.has_previous %}
#                                                 <a class="page-item pagination-prev"
#                                                    href="?page={{ page_obj.previous_page_number }}">
#                                                     Previous
#                                                 </a>
#                                             {% else %}
#                                                 <a class="page-item pagination-prev disabled" href="#">Previous</a>
#                                             {% endif %}
#
#                                             <ul class="pagination listjs-pagination mb-0">
#                                                 {% for num in paginator.page_range %}
#                                                     {% if page_obj.number == num %}
#                                                         <li class="page-item active">
#                                                             <a class="page-link"
#                                                                href="?page={{ num }}&q={{ query }}">{{ num }}</a>
#                                                         </li>
#                                                     {% else %}
#                                                         <li class="page-item">
#                                                             <a class="page-link"
#                                                                href="?page={{ num }}&q={{ query }}">{{ num }}</a>
#                                                         </li>
#                                                     {% endif %}
#                                                 {% endfor %}
#                                             </ul>
#
#
#                                             {% if page_obj.has_next %}
#                                                 <a class="page-item pagination-next"
#                                                    href="?page={{ page_obj.next_page_number }}">
#                                                     Next
#                                                 </a>
#                                             {% else %}
#                                                 <a class="page-item pagination-next disabled" href="#">Next</a>
#                                             {% endif %}
#                                         </div>
#                                     </div>
#
#
#                                 </div>
#                             </div><!-- end card -->
#                         </div>
#                         <!-- end col -->
#                     </div>
#                     <!-- end col -->
#                 </div>
#                 <!-- end row -->
#
#                 <div class="modal fade" id="showModal" tabindex="-1" aria-labelledby="exampleModalLabel"
#                      aria-hidden="true">
#                     <div class="modal-dialog modal-dialog-centered">
#                         <div class="modal-content">
#                             <div class="modal-header bg-light p-3">
#                                 <h5 class="modal-title" id="exampleModalLabel"></h5>
#                                 <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"
#                                         id="close-modal"></button>
#                             </div>
#                         </div>
#                     </div>
#                 </div>
#
#                 <!-- Modal -->
#                 <div class="modal fade zoomIn" id="deleteRecordModal" tabindex="-1" aria-hidden="true">
#                     <div class="modal-dialog modal-dialog-centered">
#                         <div class="modal-content">
#                             <div class="modal-header">
#                                 <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"
#                                         id="btn-close"></button>
#                             </div>
#                             <div class="modal-body">
#                                 <div class="mt-2 text-center">
#                                     <lord-icon src="https://cdn.lordicon.com/gsqxdxog.json" trigger="loop"
#                                                colors="primary:#25a0e2,secondary:#00bd9d"
#                                                style="width:100px;height:100px"></lord-icon>
#                                     <div class="mt-4 pt-2 fs-15 mx-4 mx-sm-5">
#                                         <h4>Are you sure ?</h4>
#                                         <p class="text-muted mx-4 mb-0">Are you sure you want to remove this record
#                                             ?</p>
#                                     </div>
#                                 </div>
#                                 <div class="d-flex gap-2 justify-content-center mt-4 mb-2">
#                                     <button type="button" class="btn w-sm btn-light" data-bs-dismiss="modal">Close
#                                     </button>
#                                     <button type="button" class="btn w-sm btn-primary" id="delete-record">Yes, Delete
#                                         It!
#                                     </button>
#                                 </div>
#                             </div>
#                         </div>
#                     </div>
#                 </div>
#                 <!--end modal -->
#             </div>
#             <!-- container-fluid -->
#         </div>
#         <!-- End Page-content -->
#         <footer class="footer">
#             <div class="container-fluid">
#                 <div class="row">
#                     <div class="col-sm-6">
#                         <script>document.write(new Date().getFullYear())</script>
#                         © Velzon.
#                     </div>
#                     <div class="col-sm-6">
#                         <div class="text-sm-end d-none d-sm-block">
#                             Design & Develop by Themesbrand
#                         </div>
#                     </div>
#                 </div>
#             </div>
#         </footer>
#     </div>
#     <!-- end main content-->
# </div>
# <!-- END layout-wrapper -->
# <!--start back-to-top-->
# <button onclick="topFunction()" class="btn btn-danger btn-icon" id="back-to-top">
#     <i class="ri-arrow-up-line"></i>
# </button>
# <!--end back-to-top-->
#
# <div class="customizer-setting d-none d-md-block">
#     <div class="btn-primary btn-rounded shadow-lg btn btn-icon btn-lg p-2" data-bs-toggle="offcanvas"
#          data-bs-target="#theme-settings-offcanvas" aria-controls="theme-settings-offcanvas">
#         <i class='mdi mdi-spin mdi-cog-outline fs-22'></i>
#     </div>
# </div>
#
# <!-- Theme Settings -->
# {% include 'Theme_Setting/Theme_Setting.html' %}
#
# <!-- JAVASCRIPT -->
# <script src="/static/assets/libs/bootstrap/js/bootstrap.bundle.min.js"></script>
# <script src="/static/assets/libs/simplebar/simplebar.min.js"></script>
# <script src="/static/assets/libs/node-waves/waves.min.js"></script>
# <script src="/static/assets/libs/feather-icons/feather.min.js"></script>
# <script src="/static/assets/js/pages/plugins/lord-icon-2.1.0.js"></script>
# <script src="/static/assets/js/plugins.js"></script>
# <!-- prismjs plugin -->
# <script src="/static/assets/libs/prismjs/prism.js"></script>
# <script src="/static/assets/libs/list.js/list.min.js"></script>
# <script src="/static/assets/libs/list.pagination.js/list.pagination.min.js"></script>
#
# <!-- listjs init -->
# <script src="/static/assets/js/pages/listjs.init.js"></script>
#
# <!-- Sweet Alerts js -->
# <script src="/static/assets/libs/sweetalert2/sweetalert2.min.js"></script>
#
# <!-- App js -->
# <script src="/static/assets/js/app.js"></script>
# <script>
#     // انتخاب همه
#     document.getElementById("checkAll").addEventListener("click", function () {
#         document.querySelectorAll(".checkItem").forEach(ch => ch.checked = this.checked);
#     });
#
#     // تابع کمکی برای بررسی خالی شدن جدول
#     function checkEmptyTable() {
#         let rows = document.querySelectorAll("#customerTable tbody tr");
#         if (rows.length === 0) {
#             document.querySelector("#customerTable tbody").innerHTML = `
#                 <tr class="empty-row">
#                     <td colspan="7">No profiles found.</td>
#                 </tr>
#             `;
#         }
#     }
#
#     // حذف چندتایی
#     function deleteMultiple() {
#         let selected = [];
#         document.querySelectorAll(".checkItem:checked").forEach(ch => {
#             selected.push(ch.value);
#         });
#
#         if (selected.length === 0) {
#             alert("هیچ کاربری انتخاب نشده!");
#             return;
#         }
#
#         if (!confirm("مطمئنی می‌خواهی این کاربران را حذف کنی؟")) return;
#
#         fetch("{% url 'dashboard:delete_profiles' %}", {
#             method: "POST",
#             headers: {
#                 "Content-Type": "application/json",
#                 "X-CSRFToken": "{{ csrf_token }}"
#             },
#             body: JSON.stringify({ids: selected})
#         })
#             .then(res => res.json())
#             .then(data => {
#                 if (data.success) {
#                     selected.forEach(id => {
#                         let row = document.querySelector(`.checkItem[value='${id}']`)?.closest("tr");
#                         if (row) row.remove();
#                     });
#                     checkEmptyTable();
#                 } else {
#                     alert("خطا در حذف کاربران");
#                 }
#             })
#             .catch(err => console.error(err));
#     }
#
#     // حذف تکی
#     document.querySelectorAll(".delete-button").forEach(btn => {
#         btn.addEventListener("click", function () {
#             let id = this.getAttribute("data-id");
#
#             if (!confirm("آیا مطمئنی می‌خواهی این کاربر حذف شود؟")) return;
#
#             fetch("{% url 'dashboard:delete_profiles' %}", {
#                 method: "POST",
#                 headers: {
#                     "Content-Type": "application/json",
#                     "X-CSRFToken": "{{ csrf_token }}"
#                 },
#                 body: JSON.stringify({ids: [id]})
#             })
#                 .then(res => res.json())
#                 .then(data => {
#                     if (data.success) {
#                         this.closest("tr").remove();
#                         checkEmptyTable();
#                     } else {
#                         alert("خطا در حذف کاربر");
#                     }
#                 })
#                 .catch(err => console.error(err));
#         });
#     });
# </script>
# <script>
#     const searchInput = document.getElementById('searchInput');
#     searchInput.value = '';
#     let timeout = null;
#
#     searchInput.addEventListener('keyup', function () {
#         clearTimeout(timeout);
#         const query = this.value;
#
#         timeout = setTimeout(() => {
#             fetch(`{% url 'dashboard:profile-approval' %}?q=${encodeURIComponent(query)}`, {
#                 headers: {"X-Requested-With": "XMLHttpRequest"}
#             })
#                 .then(res => res.text())
#                 .then(html => {
#                     const parser = new DOMParser();
#                     const doc = parser.parseFromString(html, 'text/html');
#                     const newTbody = doc.querySelector('#customerTable tbody');
#                     const tbody = document.querySelector('#customerTable tbody');
#
#                     if (newTbody && newTbody.children.length > 0) {
#                         tbody.innerHTML = newTbody.innerHTML;
#                     } else {
#                         tbody.innerHTML = `
#                     <tr>
#                         <td colspan="7" class="text-center">
#                             <div>
#                                 <lord-icon src="https://cdn.lordicon.com/msoeawqm.json" trigger="loop"
#                                            colors="primary:#25a0e2,secondary:#00bd9d"
#                                            style="width:75px;height:75px">
#                                 </lord-icon>
#                                 <h5 class="mt-2">Sorry! No Result Found</h5>
#                                 <p class="text-muted mb-0">We did not find any profiles for your search.</p>
#                             </div>
#                         </td>
#                     </tr>
#                 `;
#                     }
#                 })
#                 .catch(err => console.error(err));
#         }, 90);
#     });
# </script>
# </body>
# </html>